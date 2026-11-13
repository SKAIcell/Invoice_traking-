
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from html import escape
from pathlib import Path
import hashlib
import logging
import secrets
import uuid

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    File,
    Form,
    UploadFile,
)
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import ValidationError
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import require_roles
from app.db.session import get_db
from app.models.budget import Budget
from app.models.budget_subcategory import BudgetSubcategory
from app.models.budget_subcategory_approval_request import (
    BudgetSubcategoryApprovalRequest,
)
from app.schemas.budget_subcategory_approval_request import (
    BudgetSubcategoryRequestCreate,
    BudgetSubcategoryRequestUpdate,
    BudgetSubcategoryApprovalDecision,
    BudgetSubcategoryApprovalRequestResponse,
    BudgetSubcategoryResponse,
)
from app.services.email_service import send_email


router = APIRouter(
    prefix="/budgets",
    tags=["Budget Subcategory Allocations"],
)

logger = logging.getLogger(__name__)

TOKEN_EXPIRY_HOURS = 24


# ---------------------------------------------------------
# OPEX APPROVAL COPY UPLOAD CONFIGURATION
# ---------------------------------------------------------

BACKEND_DIR = Path(__file__).resolve().parents[3]

BUDGET_APPROVAL_COPY_DIR = (
    BACKEND_DIR / "uploads" / "budget-approval-copies"
)

ALLOWED_BUDGET_COPY_EXTENSIONS = {
    ".pdf",
    ".jpg",
    ".jpeg",
    ".png",
}

MAX_BUDGET_COPY_SIZE = 10 * 1024 * 1024

BUDGET_COPY_SIGNATURES = {
    ".pdf": b"%PDF-",
    ".jpg": b"\xff\xd8\xff",
    ".jpeg": b"\xff\xd8\xff",
    ".png": b"\x89PNG\r\n\x1a\n",
}


OPEX_CATEGORIES = {
    "AMC & IT CONSUMABLES",
    "APPLICATION SUBSCRIPTION SUPPORT",
    "INFRASTRUCTURE MANAGED SERVICES & CLOUD",
    "NETWORK CONNECTIVITY",
}


# ---------------------------------------------------------
# COMMON HELPERS
# ---------------------------------------------------------

def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_token() -> tuple[str, str, datetime]:
    raw_token = secrets.token_urlsafe(32)

    return (
        raw_token,
        token_hash(raw_token),
        utc_now() + timedelta(hours=TOKEN_EXPIRY_HOURS),
    )


def email_approval_url(token: str) -> str:
    settings = get_settings()

    base_url = (
        settings.public_backend_url
        or "http://127.0.0.1:8000"
    ).rstrip("/")

    return (
        f"{base_url}/api/budgets/"
        f"subcategory-email-approval/{token}"
    )


def validate_email_token(
    raw_token: str,
    db: Session,
) -> BudgetSubcategoryApprovalRequest:

    request = (
        db.query(BudgetSubcategoryApprovalRequest)
        .filter(
            BudgetSubcategoryApprovalRequest.approval_token_hash
            == token_hash(raw_token)
        )
        .first()
    )

    if request is None:
        raise HTTPException(
            404,
            "Invalid or expired approval link.",
        )

    ensure_pending(request)

    expiry = request.approval_token_expires_at

    if expiry is None:
        raise HTTPException(410, "Approval link has expired.")

    # MySQL may return timezone-naive datetime values.
    if expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=timezone.utc)

    if expiry < utc_now():
        raise HTTPException(410, "Approval link has expired.")

    return request


def ensure_pending(
    request: BudgetSubcategoryApprovalRequest,
) -> None:
    if request.status != "PENDING":
        raise HTTPException(
            409,
            "This approval request has already been decided.",
        )

    if request.approval_token_used_at is not None:
        raise HTTPException(
            409,
            "This approval link has already been used.",
        )


def invalidate_token(
    request: BudgetSubcategoryApprovalRequest,
) -> None:
    request.approval_token_used_at = utc_now()
    request.approval_token_hash = None


def validate_approved_amount(
    approved_amount: Decimal | None,
    planned_amount: Decimal,
) -> Decimal:

    if approved_amount is None:
        raise HTTPException(
            422,
            "IT Head must enter an approved amount.",
        )

    approved_amount = Decimal(str(approved_amount))
    planned_amount = Decimal(str(planned_amount))

    if approved_amount <= 0:
        raise HTTPException(
            422,
            "Approved amount must be greater than zero.",
        )

    if approved_amount > planned_amount:
        raise HTTPException(
            422,
            "Approved amount cannot exceed planned amount.",
        )

    return approved_amount


def get_opex_budget(
    db: Session,
    budget_id: int,
) -> Budget:

    budget = db.get(Budget, budget_id)

    if budget is None:
        raise HTTPException(404, "Budget not found.")

    if budget.budget_type != "OPEX":
        raise HTTPException(
            422,
            "Subcategory allocations are available only for OPEX budgets.",
        )

    if budget.name not in OPEX_CATEGORIES:
        raise HTTPException(
            422,
            "This budget is not one of the configured OPEX categories.",
        )

    return budget


def recalculate_parent_totals(
    db: Session,
    budget: Budget,
) -> None:

    planned_total = (
        db.query(
            func.coalesce(
                func.sum(BudgetSubcategory.planned_amount),
                0,
            )
        )
        .filter(
            BudgetSubcategory.budget_id == budget.id,
        )
        .scalar()
    )

    approved_total = (
        db.query(
            func.coalesce(
                func.sum(BudgetSubcategory.approved_amount),
                0,
            )
        )
        .filter(
            BudgetSubcategory.budget_id == budget.id,
        )
        .scalar()
    )

    budget.planned_amount = Decimal(str(planned_total or 0))
    budget.approved_amount = Decimal(str(approved_total or 0))


def ensure_no_pending_request(
    db: Session,
    budget_id: int,
    subcategory_id: int | None = None,
) -> None:

    query = db.query(BudgetSubcategoryApprovalRequest).filter(
        BudgetSubcategoryApprovalRequest.budget_id == budget_id,
        BudgetSubcategoryApprovalRequest.status == "PENDING",
    )

    if subcategory_id is not None:
        query = query.filter(
            BudgetSubcategoryApprovalRequest.subcategory_id
            == subcategory_id
        )

    if query.first():
        raise HTTPException(
            409,
            "An approval request for this allocation is already pending.",
        )


# ---------------------------------------------------------
# OPEX APPROVAL COPY VALIDATION AND STORAGE
# ---------------------------------------------------------

async def save_budget_approval_copy(
    file: UploadFile | None,
) -> str | None:

    if file is None:
        return None

    extension = Path(file.filename or "").suffix.lower()

    if extension not in ALLOWED_BUDGET_COPY_EXTENSIONS:
        raise HTTPException(
            status_code=422,
            detail="Only PDF, JPG, JPEG and PNG files are allowed.",
        )

    content = await file.read()

    if not content:
        raise HTTPException(
            status_code=422,
            detail="The uploaded approval copy is empty.",
        )

    if len(content) > MAX_BUDGET_COPY_SIZE:
        raise HTTPException(
            status_code=413,
            detail="Budget approval copy cannot exceed 10 MB.",
        )

    expected_signature = BUDGET_COPY_SIGNATURES[extension]

    if not content.startswith(expected_signature):
        raise HTTPException(
            status_code=422,
            detail="The uploaded file does not match its file extension.",
        )

    BUDGET_APPROVAL_COPY_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    stored_filename = f"{uuid.uuid4().hex}{extension}"

    destination = (
        BUDGET_APPROVAL_COPY_DIR / stored_filename
    )

    try:
        destination.write_bytes(content)

    except OSError:
        logger.exception(
            "Could not save OPEX budget approval copy."
        )

        raise HTTPException(
            status_code=500,
            detail="Could not save the budget approval copy.",
        )

    return (
        Path("uploads")
        / "budget-approval-copies"
        / stored_filename
    ).as_posix()


def delete_budget_approval_copy(
    relative_path: str | None,
) -> None:

    if not relative_path:
        return

    try:
        destination = (
            BACKEND_DIR / relative_path
        ).resolve()

        allowed_directory = (
            BUDGET_APPROVAL_COPY_DIR.resolve()
        )

        if (
            destination.is_relative_to(allowed_directory)
            and destination.is_file()
        ):
            destination.unlink()

    except OSError:
        logger.exception(
            "Could not remove unused OPEX approval copy."
        )


def get_budget_approval_email_attachments(
    request: BudgetSubcategoryApprovalRequest,
) -> list[dict]:

    if not request.approval_copy_path:
        return []

    try:
        file_path = (
            BACKEND_DIR / request.approval_copy_path
        ).resolve()

        allowed_directory = (
            BUDGET_APPROVAL_COPY_DIR.resolve()
        )

        if not file_path.is_relative_to(allowed_directory):
            logger.error(
                "Invalid OPEX approval copy path for request %s.",
                request.id,
            )
            return []

        if not file_path.is_file():
            logger.warning(
                "OPEX approval copy is missing for request %s.",
                request.id,
            )
            return []

        extension = file_path.suffix.lower()

        if extension == ".pdf":
            maintype, subtype = "application", "pdf"
        elif extension in (".jpg", ".jpeg"):
            maintype, subtype = "image", "jpeg"
        elif extension == ".png":
            maintype, subtype = "image", "png"
        else:
            return []

        return [
            {
                "filename": f"OPEX_Approval_Copy{extension}",
                "content": file_path.read_bytes(),
                "maintype": maintype,
                "subtype": subtype,
            }
        ]

    except OSError:
        logger.exception(
            "Could not read OPEX approval copy for request %s.",
            request.id,
        )
        return []


# ---------------------------------------------------------
# IT HEAD EMAIL NOTIFICATION
# ---------------------------------------------------------

def notify_it_head(
    request: BudgetSubcategoryApprovalRequest,
    raw_token: str,
    budget: Budget,
) -> None:

    settings = get_settings()

    if not settings.it_head_email:
        logger.warning(
            "IT_HEAD_EMAIL is not configured. "
            "Subcategory request %s was saved without email.",
            request.id,
        )
        return

    approval_url = escape(
        email_approval_url(raw_token),
        quote=True,
    )

    request_type = escape(request.request_type)
    category = escape(budget.name)
    subcategory_name = escape(request.name)
    financial_year = escape(budget.financial_year)
    planned_amount = escape(str(request.planned_amount))

    subject = (
        f"OPEX Allocation Approval Required - "
        f"{budget.name} / {request.name}"
    )

    html_body = f"""
    <html>
    <body style="font-family:Segoe UI,Arial,sans-serif;color:#243247;">
        <h2>OPEX Allocation Approval Required</h2>

        <p>An OPEX subcategory allocation request needs your review.</p>

        <table style="border-collapse:collapse;width:100%;max-width:650px;">
            <tr>
                <td style="padding:8px;border:1px solid #ddd;">Request ID</td>
                <td style="padding:8px;border:1px solid #ddd;">{request.id}</td>
            </tr>
            <tr>
                <td style="padding:8px;border:1px solid #ddd;">Request Type</td>
                <td style="padding:8px;border:1px solid #ddd;">{request_type}</td>
            </tr>
            <tr>
                <td style="padding:8px;border:1px solid #ddd;">Budget Category</td>
                <td style="padding:8px;border:1px solid #ddd;">{category}</td>
            </tr>
            <tr>
                <td style="padding:8px;border:1px solid #ddd;">Financial Year</td>
                <td style="padding:8px;border:1px solid #ddd;">{financial_year}</td>
            </tr>
            <tr>
                <td style="padding:8px;border:1px solid #ddd;">Subcategory</td>
                <td style="padding:8px;border:1px solid #ddd;">{subcategory_name}</td>
            </tr>
            <tr>
                <td style="padding:8px;border:1px solid #ddd;">Requested Planned Amount</td>
                <td style="padding:8px;border:1px solid #ddd;">{planned_amount}</td>
            </tr>
        </table>

        <p>The IT Head will enter the approved amount during review.</p>

        <p>
            This secure link expires in 24 hours and can only be used once.
        </p>

        <p>
            <a href="{approval_url}"
               style="display:inline-block;background:#174ea6;color:white;
                      padding:12px 20px;text-decoration:none;border-radius:4px;">
                Review Allocation Request
            </a>
        </p>

        <p>If the button does not work, copy this URL:</p>
        <p style="word-break:break-all;">{approval_url}</p>

        <p style="color:#667085;font-size:12px;">
            Skipper Limited · Finance Operations
        </p>
    </body>
    </html>
    """

    try:
        send_email(
            recipient=settings.it_head_email,
            subject=subject,
            html_body=html_body,
            attachments=get_budget_approval_email_attachments(request),
        )

        logger.info(
            "IT Head notification sent for subcategory request %s.",
            request.id,
        )

    except Exception:
        logger.exception(
            "Failed to send IT Head notification for subcategory request %s.",
            request.id,
        )


# ---------------------------------------------------------
# ACCOUNTS NOTIFICATION AFTER APPROVAL
# ---------------------------------------------------------

def notify_accounts_after_approval(
    request: BudgetSubcategoryApprovalRequest,
    budget: Budget,
    subcategory: BudgetSubcategory,
) -> None:

    settings = get_settings()
    accounts_email = settings.accounts_email

    if not accounts_email:
        logger.warning(
            "Accounts notification skipped: ACCOUNTS_EMAIL is not configured."
        )
        return

    subject = (
        f"OPEX Allocation Approved - "
        f"{budget.name} / {subcategory.name}"
    )

    html_body = f"""
    <html>
    <body style="font-family:Segoe UI,Arial,sans-serif;color:#243247;">
        <h2>OPEX Allocation Approved</h2>

        <p>The IT Head has approved the following OPEX allocation request.</p>

        <table style="border-collapse:collapse;width:100%;max-width:650px;">
            <tr>
                <td style="padding:8px;border:1px solid #ddd;">Request ID</td>
                <td style="padding:8px;border:1px solid #ddd;">{request.id}</td>
            </tr>
            <tr>
                <td style="padding:8px;border:1px solid #ddd;">Request Type</td>
                <td style="padding:8px;border:1px solid #ddd;">{escape(request.request_type)}</td>
            </tr>
            <tr>
                <td style="padding:8px;border:1px solid #ddd;">Budget Category</td>
                <td style="padding:8px;border:1px solid #ddd;">{escape(budget.name)}</td>
            </tr>
            <tr>
                <td style="padding:8px;border:1px solid #ddd;">Financial Year</td>
                <td style="padding:8px;border:1px solid #ddd;">{escape(budget.financial_year)}</td>
            </tr>
            <tr>
                <td style="padding:8px;border:1px solid #ddd;">Subcategory</td>
                <td style="padding:8px;border:1px solid #ddd;">{escape(subcategory.name)}</td>
            </tr>
            <tr>
                <td style="padding:8px;border:1px solid #ddd;">Planned Allocation</td>
                <td style="padding:8px;border:1px solid #ddd;">{subcategory.planned_amount}</td>
            </tr>
            <tr>
                <td style="padding:8px;border:1px solid #ddd;">Approved Allocation</td>
                <td style="padding:8px;border:1px solid #ddd;">{subcategory.approved_amount}</td>
            </tr>
            <tr>
                <td style="padding:8px;border:1px solid #ddd;">Parent Planned Total</td>
                <td style="padding:8px;border:1px solid #ddd;">{budget.planned_amount}</td>
            </tr>
            <tr>
                <td style="padding:8px;border:1px solid #ddd;">Parent Approved Total</td>
                <td style="padding:8px;border:1px solid #ddd;">{budget.approved_amount}</td>
            </tr>
        </table>

        <p><strong>IT Head Remarks:</strong> {escape(request.remarks or "No remarks")}</p>

        <p>Please proceed with the necessary Accounts processing.</p>

        <p style="color:#667085;font-size:12px;">
            Skipper Limited · Finance Operations
        </p>
    </body>
    </html>
    """

    try:
        send_email(
            recipient=accounts_email,
            subject=subject,
            html_body=html_body,
        )

        logger.info(
            "Accounts notification sent for OPEX subcategory request %s.",
            request.id,
        )

    except Exception:
        logger.exception(
            "Failed to send Accounts notification for OPEX subcategory request %s.",
            request.id,
        )


# ---------------------------------------------------------
# SUBMIT CREATE SUBCATEGORY REQUEST
# ADMIN / ACCOUNTS
# ---------------------------------------------------------

@router.post(
    "/{budget_id}/subcategories/requests",
    response_model=BudgetSubcategoryApprovalRequestResponse,
    status_code=201,
)
async def request_subcategory_creation(
    budget_id: int,
    name: str = Form(...),
    planned_amount: str = Form(...),
    approval_copy: UploadFile | None = File(None),
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("ADMIN", "ACCOUNTS")),
):

    try:
        payload = BudgetSubcategoryRequestCreate(
            name=name,
            planned_amount=planned_amount,
        )

    except ValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail=exc.errors(),
        )

    budget = get_opex_budget(db, budget_id)

    name = payload.name.strip()

    if not name:
        raise HTTPException(422, "Subcategory name cannot be blank.")

    existing = db.query(BudgetSubcategory).filter(
        BudgetSubcategory.budget_id == budget_id,
        func.lower(BudgetSubcategory.name) == name.lower(),
    ).first()

    if existing:
        raise HTTPException(
            409,
            "This subcategory already exists under the selected category.",
        )

    pending = db.query(BudgetSubcategoryApprovalRequest).filter(
        BudgetSubcategoryApprovalRequest.budget_id == budget_id,
        BudgetSubcategoryApprovalRequest.status == "PENDING",
        BudgetSubcategoryApprovalRequest.request_type == "CREATE",
        func.lower(BudgetSubcategoryApprovalRequest.name) == name.lower(),
    ).first()

    if pending:
        raise HTTPException(
            409,
            "A creation request for this subcategory is already pending.",
        )

    approval_copy_path = await save_budget_approval_copy(
        approval_copy
    )

    raw_token, digest, expiry = generate_token()

    request = BudgetSubcategoryApprovalRequest(
        budget_id=budget.id,
        subcategory_id=None,
        request_type="CREATE",
        status="PENDING",
        name=name,
        planned_amount=payload.planned_amount,
        approved_amount=None,
        requested_by_id=current_user.id,
        approval_token_hash=digest,
        approval_token_expires_at=expiry,
        approval_copy_path=approval_copy_path,
    )

    db.add(request)

    try:
        db.commit()
        db.refresh(request)

    except IntegrityError:
        db.rollback()
        delete_budget_approval_copy(approval_copy_path)

        raise HTTPException(
            409,
            "Could not create the subcategory approval request.",
        )

    except Exception:
        db.rollback()
        delete_budget_approval_copy(approval_copy_path)
        raise

    notify_it_head(request, raw_token, budget)

    return request


# ---------------------------------------------------------
# LIST ACTIVE SUBCATEGORIES
# ADMIN / ACCOUNTS
# ---------------------------------------------------------

@router.get(
    "/{budget_id}/subcategories",
    response_model=list[BudgetSubcategoryResponse],
)
def list_subcategories(
    budget_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("ADMIN", "ACCOUNTS")),
):

    get_opex_budget(db, budget_id)

    return (
        db.query(BudgetSubcategory)
        .filter(BudgetSubcategory.budget_id == budget_id)
        .order_by(BudgetSubcategory.name.asc())
        .all()
    )


# ---------------------------------------------------------
# VIEW APPROVED OPEX SUBCATEGORY APPROVAL COPY
# ADMIN / ACCOUNTS / IT HEAD
# ---------------------------------------------------------

@router.get(
    "/subcategories/{subcategory_id}/approval-copy",
)
def view_subcategory_approval_copy(
    subcategory_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(
        require_roles("ADMIN", "ACCOUNTS", "IT_HEAD")
    ),
):

    subcategory = db.get(
        BudgetSubcategory,
        subcategory_id,
    )

    if subcategory is None:
        raise HTTPException(
            404,
            "OPEX subcategory allocation not found.",
        )

    if not subcategory.approval_copy_path:
        raise HTTPException(
            404,
            "No approval copy is attached to this subcategory.",
        )

    file_path = (
        BACKEND_DIR / subcategory.approval_copy_path
    ).resolve()

    allowed_directory = BUDGET_APPROVAL_COPY_DIR.resolve()

    if not file_path.is_relative_to(allowed_directory):
        logger.error(
            "Invalid OPEX approval copy path for subcategory %s.",
            subcategory_id,
        )

        raise HTTPException(
            400,
            "Invalid approval copy path.",
        )

    if not file_path.is_file():
        raise HTTPException(
            404,
            "OPEX approval copy file not found.",
        )

    extension = file_path.suffix.lower()

    media_types = {
        ".pdf": "application/pdf",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
    }

    media_type = media_types.get(extension)

    if not media_type:
        raise HTTPException(
            415,
            "Unsupported approval copy format.",
        )

    return FileResponse(
        path=file_path,
        media_type=media_type,
        filename=f"OPEX_Approval_Copy{extension}",
        content_disposition_type="inline",
    )


# ---------------------------------------------------------
# SUBMIT SUBCATEGORY UPDATE REQUEST
# ADMIN / ACCOUNTS
# ---------------------------------------------------------

@router.patch(
    "/subcategories/{subcategory_id}/requests",
    response_model=BudgetSubcategoryApprovalRequestResponse,
    status_code=201,
)
def request_subcategory_update(
    subcategory_id: int,
    payload: BudgetSubcategoryRequestUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("ADMIN", "ACCOUNTS")),
):

    subcategory = db.get(BudgetSubcategory, subcategory_id)

    if subcategory is None:
        raise HTTPException(404, "Subcategory allocation not found.")

    budget = get_opex_budget(db, subcategory.budget_id)

    ensure_no_pending_request(
        db,
        budget.id,
        subcategory.id,
    )

    raw_token, digest, expiry = generate_token()

    request = BudgetSubcategoryApprovalRequest(
        budget_id=budget.id,
        subcategory_id=subcategory.id,
        request_type="UPDATE",
        status="PENDING",
        name=subcategory.name,
        planned_amount=payload.planned_amount,
        approved_amount=None,
        requested_by_id=current_user.id,
        approval_token_hash=digest,
        approval_token_expires_at=expiry,
    )

    db.add(request)

    try:
        db.commit()
        db.refresh(request)

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            409,
            "Could not create the subcategory update request.",
        )

    notify_it_head(request, raw_token, budget)

    return request


# ---------------------------------------------------------
# REQUESTER: LIST OWN SUBCATEGORY REQUEST HISTORY
# ADMIN / ACCOUNTS
# ---------------------------------------------------------

@router.get(
    "/subcategory-approval-requests/mine",
    response_model=list[BudgetSubcategoryApprovalRequestResponse],
)
def list_my_subcategory_requests(
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("ADMIN", "ACCOUNTS")),
):

    return (
        db.query(BudgetSubcategoryApprovalRequest)
        .filter(
            BudgetSubcategoryApprovalRequest.requested_by_id
            == current_user.id
        )
        .order_by(
            BudgetSubcategoryApprovalRequest.requested_at.desc()
        )
        .all()
    )


# ---------------------------------------------------------
# IT HEAD: LIST PENDING SUBCATEGORY REQUESTS
# ---------------------------------------------------------

@router.get(
    "/subcategory-approval-requests/pending",
    response_model=list[BudgetSubcategoryApprovalRequestResponse],
)
def list_pending_subcategory_requests(
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("IT_HEAD")),
):

    return (
        db.query(BudgetSubcategoryApprovalRequest)
        .filter(
            BudgetSubcategoryApprovalRequest.status == "PENDING"
        )
        .order_by(
            BudgetSubcategoryApprovalRequest.requested_at.asc()
        )
        .all()
    )


# ---------------------------------------------------------
# PROCESS APPROVAL / REJECTION
# ---------------------------------------------------------

def process_decision(
    request: BudgetSubcategoryApprovalRequest,
    decision: str,
    payload: BudgetSubcategoryApprovalDecision,
    db: Session,
    decided_by_id: int | None,
):

    budget = (
        db.query(Budget)
        .filter(Budget.id == request.budget_id)
        .with_for_update()
        .first()
    )

    if budget is None:
        raise HTTPException(404, "Parent budget not found.")

    if budget.budget_type != "OPEX":
        raise HTTPException(
            422,
            "Subcategory allocations are available only for OPEX budgets.",
        )

    subcategory = None

    if decision == "approve":

        approved_amount = validate_approved_amount(
            payload.approved_amount,
            request.planned_amount,
        )

        if request.request_type == "CREATE":

            existing = db.query(BudgetSubcategory).filter(
                BudgetSubcategory.budget_id == budget.id,
                func.lower(BudgetSubcategory.name)
                == request.name.lower(),
            ).first()

            if existing:
                raise HTTPException(
                    409,
                    "This subcategory already exists under the selected category.",
                )

            subcategory = BudgetSubcategory(
                budget_id=budget.id,
                name=request.name,
                planned_amount=request.planned_amount,
                approved_amount=approved_amount,
                approval_copy_path=request.approval_copy_path,
            )

            db.add(subcategory)
            db.flush()

            request.subcategory_id = subcategory.id

        elif request.request_type == "UPDATE":

            if request.subcategory_id is None:
                raise HTTPException(
                    409,
                    "The update request is missing its subcategory reference.",
                )

            subcategory = (
                db.query(BudgetSubcategory)
                .filter(
                    BudgetSubcategory.id == request.subcategory_id,
                    BudgetSubcategory.budget_id == budget.id,
                )
                .with_for_update()
                .first()
            )

            if subcategory is None:
                raise HTTPException(
                    404,
                    "The subcategory associated with this request no longer exists.",
                )

            subcategory.planned_amount = request.planned_amount
            subcategory.approved_amount = approved_amount

        else:
            raise HTTPException(
                422,
                "Unsupported subcategory request type.",
            )

        request.approved_amount = approved_amount
        request.status = "APPROVED"

        recalculate_parent_totals(db, budget)

    elif decision == "reject":

        request.status = "REJECTED"

        # Rejection deliberately leaves the active allocation
        # and parent totals unchanged.

    else:
        raise HTTPException(
            422,
            "Decision must be approve or reject.",
        )

    request.decided_by_id = decided_by_id
    request.decided_at = utc_now()
    request.remarks = payload.remarks

    invalidate_token(request)

    try:
        db.commit()
        db.refresh(request)

        if budget is not None:
            db.refresh(budget)

        if subcategory is not None:
            db.refresh(subcategory)

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            409,
            "Could not save the subcategory approval decision.",
        )

    if decision == "approve" and subcategory is not None:
        notify_accounts_after_approval(
            request,
            budget,
            subcategory,
        )

        return {
            "message": "OPEX subcategory allocation approved successfully.",
            "request_id": request.id,
            "budget_id": budget.id,
            "subcategory_id": subcategory.id,
            "planned_amount": str(subcategory.planned_amount),
            "approved_amount": str(subcategory.approved_amount),
            "parent_planned_total": str(budget.planned_amount),
            "parent_approved_total": str(budget.approved_amount),
        }

    return {
        "message": "OPEX subcategory allocation request rejected.",
        "request_id": request.id,
        "budget_id": budget.id,
    }


# ---------------------------------------------------------
# IT HEAD: APPROVE SUBCATEGORY REQUEST
# ---------------------------------------------------------

@router.post(
    "/subcategory-approval-requests/{request_id}/approve",
)
def approve_subcategory_request(
    request_id: int,
    payload: BudgetSubcategoryApprovalDecision,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("IT_HEAD")),
):

    request = (
        db.query(BudgetSubcategoryApprovalRequest)
        .filter(
            BudgetSubcategoryApprovalRequest.id == request_id
        )
        .with_for_update()
        .first()
    )

    if request is None:
        raise HTTPException(404, "Approval request not found.")

    ensure_pending(request)

    return process_decision(
        request=request,
        decision="approve",
        payload=payload,
        db=db,
        decided_by_id=current_user.id,
    )


# ---------------------------------------------------------
# IT HEAD: REJECT SUBCATEGORY REQUEST
# ---------------------------------------------------------

@router.post(
    "/subcategory-approval-requests/{request_id}/reject",
)
def reject_subcategory_request(
    request_id: int,
    payload: BudgetSubcategoryApprovalDecision,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("IT_HEAD")),
):

    request = (
        db.query(BudgetSubcategoryApprovalRequest)
        .filter(
            BudgetSubcategoryApprovalRequest.id == request_id
        )
        .with_for_update()
        .first()
    )

    if request is None:
        raise HTTPException(404, "Approval request not found.")

    ensure_pending(request)

    return process_decision(
        request=request,
        decision="reject",
        payload=payload,
        db=db,
        decided_by_id=current_user.id,
    )


# ---------------------------------------------------------
# SECURE EMAIL APPROVAL REVIEW PAGE
# ---------------------------------------------------------

@router.get(
    "/subcategory-email-approval/{token}",
    response_class=HTMLResponse,
)
def email_approval_page(
    token: str,
    db: Session = Depends(get_db),
):
    request = validate_email_token(token, db)
    budget = db.get(Budget, request.budget_id)

    if budget is None:
        raise HTTPException(404, "Parent budget not found.")

    safe_token = escape(token, quote=True)
    safe_planned_amount = escape(str(request.planned_amount), quote=True)

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>OPEX Allocation Approval</title>

        <style>
            body {{
                font-family: Segoe UI, Arial, sans-serif;
                background: #f3f5f8;
                color: #243247;
                padding: 30px;
            }}

            .container {{
                max-width: 650px;
                margin: 30px auto;
                background: white;
                padding: 30px;
                border-radius: 8px;
                box-shadow: 0 4px 20px rgba(0,0,0,.08);
            }}

            table {{
                width: 100%;
                border-collapse: collapse;
                margin-bottom: 20px;
            }}

            td {{
                padding: 10px;
                border: 1px solid #ddd;
            }}

            input, textarea {{
                width: 100%;
                box-sizing: border-box;
                padding: 10px;
                margin-top: 8px;
                border: 1px solid #cbd5e1;
                border-radius: 4px;
                font: inherit;
            }}

            textarea {{
                min-height: 100px;
            }}

            button {{
                padding: 12px 22px;
                border: 0;
                border-radius: 4px;
                cursor: pointer;
                color: white;
                font-weight: 600;
                margin: 8px 8px 0 0;
            }}

            button:disabled {{
                opacity: .6;
                cursor: not-allowed;
            }}

            .approve {{
                background: #198754;
            }}

            .reject {{
                background: #b42318;
            }}

            #result {{
                margin-top: 20px;
                font-weight: 600;
                overflow-wrap: anywhere;
            }}
        </style>
    </head>

    <body>
        <div class="container">
            <h2>OPEX Allocation Approval</h2>
            <p>Review the request and decide the approved allocation.</p>

            <table>
                <tr><td>Request ID</td><td>{request.id}</td></tr>
                <tr><td>Request Type</td><td>{escape(str(request.request_type))}</td></tr>
                <tr><td>Budget Category</td><td>{escape(budget.name)}</td></tr>
                <tr><td>Financial Year</td><td>{escape(budget.financial_year)}</td></tr>
                <tr><td>Subcategory</td><td>{escape(request.name)}</td></tr>
                <tr><td>Planned Amount</td><td>{safe_planned_amount}</td></tr>
            </table>

            <label for="approved_amount">Approved Amount (IT Head)</label>
            <input
                id="approved_amount"
                type="number"
                min="0.01"
                max="{safe_planned_amount}"
                step="0.01"
                value="{safe_planned_amount}"
                required
            >

            <label for="remarks">Remarks (optional)</label>
            <textarea
                id="remarks"
                maxlength="2000"
                placeholder="Enter approval or rejection remarks"
            ></textarea>

            <div>
                <button class="approve" onclick="submitDecision('approve')">
                    Approve
                </button>

                <button class="reject" onclick="submitDecision('reject')">
                    Reject
                </button>
            </div>

            <div id="result"></div>

            <p style="color:#667085;font-size:12px;">
                Skipper Limited · Finance Operations
            </p>
        </div>

        <script>
            const token = "{safe_token}";

            async function submitDecision(action) {{
                const result = document.getElementById("result");
                const approvedInput = document.getElementById("approved_amount");
                const approvedAmount = approvedInput.value;
                const remarks = document.getElementById("remarks").value;

                if (action === "reject" &&
                    !confirm("Are you sure you want to reject this request?")) {{
                    return;
                }}

                if (action === "approve") {{
                    if (approvedAmount === "") {{
                        result.textContent = "Please enter the approved amount.";
                        return;
                    }}

                    if (
                        !Number.isFinite(Number(approvedAmount)) ||
                        Number(approvedAmount) <= 0 ||
                        Number(approvedAmount) > Number("{safe_planned_amount}")
                    ) {{
                        result.textContent =
                            "Approved amount must be greater than zero and cannot exceed planned amount.";
                        return;
                    }}

                    if (!confirm("Approve this allocation with the entered amount?")) {{
                        return;
                    }}
                }}

                result.textContent = "Processing decision...";

                const body = {{ remarks: remarks }};

                if (action === "approve") {{
                    body.approved_amount = approvedAmount;
                }}

                try {{
                    const response = await fetch(
                        `/api/budgets/subcategory-email-approval/${{token}}/${{action}}`,
                        {{
                            method: "POST",
                            headers: {{ "Content-Type": "application/json" }},
                            body: JSON.stringify(body)
                        }}
                    );

                    const responseText = await response.text();
                    let data = {{}};

                    try {{
                        data = responseText ? JSON.parse(responseText) : {{}};
                    }} catch {{
                        data = {{ detail: responseText }};
                    }}

                    if (!response.ok) {{
                        throw new Error(
                            data.detail || data.message ||
                            `Request failed with status ${{response.status}}`
                        );
                    }}

                    result.textContent =
                        data.message || "Decision processed successfully.";

                    document.querySelectorAll("button").forEach(
                        button => button.disabled = true
                    );

                }} catch (error) {{
                    result.textContent =
                        error.message || "Unable to process decision.";
                }}
            }}
        </script>
    </body>
    </html>
    """

    return HTMLResponse(content=html)


# ---------------------------------------------------------
# PROCESS EMAIL APPROVAL DECISION
# ---------------------------------------------------------

@router.post("/subcategory-email-approval/{token}/approve")
def approve_subcategory_by_email(
    token: str,
    payload: BudgetSubcategoryApprovalDecision,
    db: Session = Depends(get_db),
):

    request = validate_email_token(token, db)

    return process_decision(
        request=request,
        decision="approve",
        payload=payload,
        db=db,
        decided_by_id=None,
    )


@router.post("/subcategory-email-approval/{token}/reject")
def reject_subcategory_by_email(
    token: str,
    payload: BudgetSubcategoryApprovalDecision,
    db: Session = Depends(get_db),
):

    request = validate_email_token(token, db)

    return process_decision(
        request=request,
        decision="reject",
        payload=payload,
        db=db,
        decided_by_id=None,
    )
