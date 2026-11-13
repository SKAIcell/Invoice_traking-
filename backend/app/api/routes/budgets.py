
from datetime import datetime, timedelta, date
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
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import require_roles
from app.db.session import get_db
from app.models.budget import Budget
from app.models.budget_approval_request import BudgetApprovalRequest
from app.schemas.budget import BudgetCreate, BudgetUpdate, BudgetResponse
from app.schemas.budget_approval_request import (
    BudgetApprovalRequestResponse,
    BudgetApprovalDecision,
)
from app.services.email_service import send_email



router = APIRouter(prefix="/budgets", tags=["Budgets"])

logger = logging.getLogger(__name__)



# ---------------------------------------------------------
# BUDGET APPROVAL COPY UPLOAD CONFIGURATION
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


TOKEN_EXPIRY_HOURS = 24


# ---------------------------------------------------------
# AUTOMATIC OPEX PARENT CATEGORIES
# ---------------------------------------------------------

OPEX_CATEGORIES = [
    "AMC & IT CONSUMABLES",
    "APPLICATION SUBSCRIPTION SUPPORT",
    "INFRASTRUCTURE MANAGED SERVICES & CLOUD",
    "NETWORK CONNECTIVITY",
]


def get_current_financial_year() -> str:
    """
    Financial year runs from April to March.
    Example: November 2026 -> 2026-2027.
    """

    today = date.today()

    if today.month >= 4:
        start_year = today.year
    else:
        start_year = today.year - 1

    return f"{start_year}-{start_year + 1}"


def ensure_opex_categories(
    db: Session,
    financial_year: str,
) -> None:
    """
    Ensure all four OPEX parent categories exist for the
    requested financial year.

    Parent amounts start at zero. Actual OPEX amounts are
    derived from approved subcategory allocations.
    """

    created = False

    for category_name in OPEX_CATEGORIES:
        existing = db.query(Budget).filter(
            Budget.name == category_name,
            Budget.financial_year == financial_year,
            Budget.budget_type == "OPEX",
        ).first()

        if existing:
            continue

        category = Budget(
            name=category_name,
            financial_year=financial_year,
            budget_type="OPEX",
            planned_amount=Decimal("0.00"),
            approved_amount=Decimal("0.00"),
        )

        db.add(category)
        created = True

    if created:
        try:
            db.commit()

        except IntegrityError:
            # Another request may have created the same
            # category concurrently.
            db.rollback()

            logger.warning(
                "OPEX categories may have been created "
                "concurrently for FY %s.",
                financial_year,
            )



# ---------------------------------------------------------
# BUDGET APPROVAL COPY VALIDATION AND STORAGE
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
            "Could not save budget approval copy."
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
            "Could not remove unused budget approval copy."
        )




# ---------------------------------------------------------
# COMMON HELPERS
# ---------------------------------------------------------


def validate_approved_amount(
    approved_amount: Decimal | None,
    planned_amount: Decimal,
) -> Decimal:

    if approved_amount is None:
        raise HTTPException(
            status_code=422,
            detail="IT Head must enter an approved amount.",
        )

    approved_amount = Decimal(str(approved_amount))
    planned_amount = Decimal(str(planned_amount))

    if approved_amount <= 0:
        raise HTTPException(
            status_code=422,
            detail="Approved amount must be greater than zero.",
        )

    if approved_amount > planned_amount:
        raise HTTPException(
            status_code=422,
            detail="Approved amount cannot exceed planned amount.",
        )

    return approved_amount


def generate_approval_token() -> tuple[str, str, datetime]:
    raw_token = secrets.token_urlsafe(32)

    token_hash = hashlib.sha256(
        raw_token.encode("utf-8")
    ).hexdigest()

    expires_at = datetime.utcnow() + timedelta(
        hours=TOKEN_EXPIRY_HOURS
    )

    return raw_token, token_hash, expires_at


def hash_approval_token(raw_token: str) -> str:
    return hashlib.sha256(
        raw_token.encode("utf-8")
    ).hexdigest()


def get_email_approval_url(raw_token: str) -> str:
    settings = get_settings()

    base_url = (
        settings.public_backend_url
        or "http://127.0.0.1:8000"
    ).rstrip("/")

    return (
        f"{base_url}/api/budgets/"
        f"email-approval/{raw_token}"
    )


def validate_email_approval_token(
    raw_token: str,
    db: Session,
) -> BudgetApprovalRequest:

    token_hash = hash_approval_token(raw_token)

    request = db.query(BudgetApprovalRequest).filter(
        BudgetApprovalRequest.approval_token_hash == token_hash,
    ).first()

    if not request:
        raise HTTPException(
            status_code=404,
            detail="Invalid approval link.",
        )

    if request.status != "PENDING":
        raise HTTPException(
            status_code=409,
            detail="This approval request has already been decided.",
        )

    if request.approval_token_used_at is not None:
        raise HTTPException(
            status_code=409,
            detail="This approval link has already been used.",
        )

    if (
        request.approval_token_expires_at is None
        or request.approval_token_expires_at < datetime.utcnow()
    ):
        raise HTTPException(
            status_code=410,
            detail="This approval link has expired.",
        )

    return request


def invalidate_approval_token(
    request: BudgetApprovalRequest,
) -> None:
    request.approval_token_used_at = datetime.utcnow()
    request.approval_token_hash = None


def ensure_request_pending(
    request: BudgetApprovalRequest,
) -> None:

    if request.status != "PENDING":
        raise HTTPException(
            status_code=409,
            detail="This approval request has already been decided.",
        )


# ---------------------------------------------------------
# ACCOUNTS EMAIL NOTIFICATION AFTER APPROVAL
# ---------------------------------------------------------

def notify_accounts_after_budget_approval(
    request: BudgetApprovalRequest,
    budget: Budget,
) -> None:
    """
    Notify Accounts after a budget approval has been committed.

    Email failure must not undo the successful approval.
    This function is called only for APPROVED requests.
    """

    settings = get_settings()
    accounts_email = settings.accounts_email

    if not accounts_email:
        logger.warning(
            "Accounts email is not configured. "
            "Budget approval request %s was approved "
            "without Accounts notification.",
            request.id,
        )
        return

    request_name = escape(request.name)
    request_type = escape(request.request_type)
    budget_type = escape(request.budget_type)
    financial_year = escape(request.financial_year)

    planned_amount = escape(
        str(request.planned_amount)
    )

    approved_amount = escape(
        str(request.approved_amount)
    )

    remarks = escape(
        request.remarks or "No remarks provided."
    )

    subject = (
        f"Budget Approved - {request.name} "
        f"({request.financial_year})"
    )

    html_body = f"""
    <html>
    <body style="font-family:Segoe UI,Arial,sans-serif;color:#243247;">
        <h2>Budget Approval Notification</h2>

        <p>
            The IT Head has approved the following budget request.
        </p>

        <table style="border-collapse:collapse;width:100%;max-width:650px;">
            <tr>
                <td style="padding:8px;border:1px solid #ddd;">
                    Request ID
                </td>
                <td style="padding:8px;border:1px solid #ddd;">
                    {request.id}
                </td>
            </tr>

            <tr>
                <td style="padding:8px;border:1px solid #ddd;">
                    Request Type
                </td>
                <td style="padding:8px;border:1px solid #ddd;">
                    {request_type}
                </td>
            </tr>

            <tr>
                <td style="padding:8px;border:1px solid #ddd;">
                    Budget Name
                </td>
                <td style="padding:8px;border:1px solid #ddd;">
                    {request_name}
                </td>
            </tr>

            <tr>
                <td style="padding:8px;border:1px solid #ddd;">
                    Financial Year
                </td>
                <td style="padding:8px;border:1px solid #ddd;">
                    {financial_year}
                </td>
            </tr>

            <tr>
                <td style="padding:8px;border:1px solid #ddd;">
                    Budget Type
                </td>
                <td style="padding:8px;border:1px solid #ddd;">
                    {budget_type}
                </td>
            </tr>

            <tr>
                <td style="padding:8px;border:1px solid #ddd;">
                    Planned Amount
                </td>
                <td style="padding:8px;border:1px solid #ddd;">
                    {planned_amount}
                </td>
            </tr>

            <tr>
                <td style="padding:8px;border:1px solid #ddd;">
                    Approved Amount
                </td>
                <td style="padding:8px;border:1px solid #ddd;">
                    {approved_amount}
                </td>
            </tr>

            <tr>
                <td style="padding:8px;border:1px solid #ddd;">
                    Approval Remarks
                </td>
                <td style="padding:8px;border:1px solid #ddd;">
                    {remarks}
                </td>
            </tr>
        </table>

        <p>
            The budget approval has been completed successfully.
        </p>

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
            "Accounts notification sent for approved "
            "budget request %s.",
            request.id,
        )

    except Exception:
        logger.exception(
            "Accounts notification failed for approved "
            "budget request %s. Approval remains successful.",
            request.id,
        )



# ---------------------------------------------------------
# PREPARE BUDGET APPROVAL COPY EMAIL ATTACHMENT
# ---------------------------------------------------------

def get_budget_approval_email_attachments(
    request: BudgetApprovalRequest,
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
                "Invalid budget approval copy path for request %s.",
                request.id,
            )
            return []

        if not file_path.is_file():
            logger.warning(
                "Budget approval copy is missing for request %s.",
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
                "filename": f"Budget_Approval_Copy{extension}",
                "content": file_path.read_bytes(),
                "maintype": maintype,
                "subtype": subtype,
            }
        ]

    except OSError:
        logger.exception(
            "Could not read budget approval copy for request %s.",
            request.id,
        )
        return []


# ---------------------------------------------------------
# IT HEAD EMAIL NOTIFICATION
# ---------------------------------------------------------

def notify_it_head(
    request: BudgetApprovalRequest,
    raw_token: str,
) -> None:

    settings = get_settings()

    if not settings.it_head_email:
        logger.warning(
            "IT Head email is not configured. "
            "Approval request %s was saved without email notification.",
            request.id,
        )
        return

    approval_url = escape(
        get_email_approval_url(raw_token),
        quote=True,
    )

    request_type = escape(request.request_type)
    budget_name = escape(request.name)
    financial_year = escape(request.financial_year)
    budget_type = escape(request.budget_type)
    planned_amount = escape(str(request.planned_amount))

    subject = (
        f"Budget {request_type} Approval Required - "
        f"{request.name}"
    )

    html_body = f"""
    <html>
    <body style="font-family:Segoe UI,Arial,sans-serif;color:#243247;">
        <h2>Budget Approval Required</h2>

        <p>A budget request has been submitted for your review.</p>

        <table style="border-collapse:collapse;width:100%;max-width:600px;">
            <tr>
                <td style="padding:8px;border:1px solid #ddd;">Request ID</td>
                <td style="padding:8px;border:1px solid #ddd;">{request.id}</td>
            </tr>
            <tr>
                <td style="padding:8px;border:1px solid #ddd;">Request Type</td>
                <td style="padding:8px;border:1px solid #ddd;">{request_type}</td>
            </tr>
            <tr>
                <td style="padding:8px;border:1px solid #ddd;">Budget Name</td>
                <td style="padding:8px;border:1px solid #ddd;">{budget_name}</td>
            </tr>
            <tr>
                <td style="padding:8px;border:1px solid #ddd;">Financial Year</td>
                <td style="padding:8px;border:1px solid #ddd;">{financial_year}</td>
            </tr>
            <tr>
                <td style="padding:8px;border:1px solid #ddd;">Budget Type</td>
                <td style="padding:8px;border:1px solid #ddd;">{budget_type}</td>
            </tr>
            <tr>
                <td style="padding:8px;border:1px solid #ddd;">Requested Planned Amount</td>
                <td style="padding:8px;border:1px solid #ddd;">{planned_amount}</td>
            </tr>
        </table>

        <p>
            The approved amount will be decided by the IT Head during review.
        </p>

        <p>
            This request is currently <strong>PENDING</strong>.
            The approval link expires in 24 hours and can only be used once.
        </p>

        <p>
            <a href="{approval_url}"
               style="display:inline-block;background:#174ea6;color:white;
                      padding:12px 20px;text-decoration:none;border-radius:4px;">
                Review Budget Request
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
            "Notification sent for budget approval request %s.",
            request.id,
        )

    except Exception:
        logger.exception(
            "Email notification failed for budget approval request %s.",
            request.id,
        )

# ---------------------------------------------------------
# CREATE BUDGET APPROVAL REQUEST
# CAPEX GENERAL REQUESTS ONLY
# ---------------------------------------------------------


@router.post(
    "",
    response_model=BudgetApprovalRequestResponse,
    status_code=201,
)
async def create_budget(
    name: str = Form(...),
    financial_year: str = Form(...),
    budget_type: str = Form(...),
    planned_amount: str = Form(...),
    approval_copy: UploadFile | None = File(None),
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("ADMIN", "ACCOUNTS")),
):
    # Validate all normal budget fields using the existing schema.
    try:
        payload = BudgetCreate(
            name=name,
            financial_year=financial_year,
            budget_type=budget_type,
            planned_amount=planned_amount,
        )
    except ValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail=exc.errors(),
        )

    if payload.budget_type == "OPEX":
        raise HTTPException(
            status_code=422,
            detail=(
                "OPEX parent budgets are system-managed. "
                "Submit an OPEX subcategory allocation request "
                "instead."
            ),
        )

    existing = db.query(Budget).filter(
        Budget.name == payload.name,
        Budget.financial_year == payload.financial_year,
        Budget.budget_type == payload.budget_type,
    ).first()

    if existing:
        raise HTTPException(
            status_code=409,
            detail="Budget already exists for this financial year and budget type.",
        )

    pending = db.query(BudgetApprovalRequest).filter(
        BudgetApprovalRequest.request_type == "CREATE",
        BudgetApprovalRequest.status == "PENDING",
        BudgetApprovalRequest.name == payload.name,
        BudgetApprovalRequest.financial_year == payload.financial_year,
        BudgetApprovalRequest.budget_type == payload.budget_type,
    ).first()

    if pending:
        raise HTTPException(
            status_code=409,
            detail="A budget creation request is already pending approval.",
        )

    # Save the optional approval copy.
    approval_copy_path = await save_budget_approval_copy(
        approval_copy
    )

    raw_token, token_hash, expires_at = generate_approval_token()

    request = BudgetApprovalRequest(
        budget_id=None,
        request_type="CREATE",
        status="PENDING",
        name=payload.name,
        financial_year=payload.financial_year,
        budget_type=payload.budget_type,
        planned_amount=payload.planned_amount,
        approved_amount=None,
        requested_by_id=current_user.id,
        approval_token_hash=token_hash,
        approval_token_expires_at=expires_at,
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
            status_code=409,
            detail="Budget approval request violates a database constraint.",
        )

    except Exception:
        db.rollback()
        delete_budget_approval_copy(approval_copy_path)
        raise

    notify_it_head(request, raw_token)

    return request

# ---------------------------------------------------------
# LIST ACTIVE BUDGETS
# ---------------------------------------------------------

@router.get("", response_model=list[BudgetResponse])
def list_budgets(
    financial_year: str | None = None,
    budget_type: str | None = None,
    db: Session = Depends(get_db),
    current_user=Depends(
        require_roles("ADMIN", "ACCOUNTS", "IT_HEAD")
    ),
):

    requested_year = (
        financial_year
        or get_current_financial_year()
    )

    ensure_opex_categories(
        db=db,
        financial_year=requested_year,
    )

    query = db.query(Budget)

    if financial_year:
        query = query.filter(
            Budget.financial_year == financial_year
        )

    if budget_type:
        budget_type = budget_type.upper()

        if budget_type not in ("OPEX", "CAPEX"):
            raise HTTPException(
                status_code=422,
                detail="Budget type must be OPEX or CAPEX.",
            )

        query = query.filter(
            Budget.budget_type == budget_type
        )

    return query.order_by(
        Budget.financial_year.desc(),
        Budget.id.desc(),
    ).all()



# ---------------------------------------------------------
# VIEW APPROVED BUDGET APPROVAL COPY
# ---------------------------------------------------------

@router.get("/{budget_id}/approval-copy")
def view_budget_approval_copy(
    budget_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(
        require_roles("ADMIN", "ACCOUNTS", "IT_HEAD")
    ),
):
    budget = db.get(Budget, budget_id)

    if not budget:
        raise HTTPException(
            status_code=404,
            detail="Budget not found.",
        )

    if not budget.approval_copy_path:
        raise HTTPException(
            status_code=404,
            detail="No approval copy is attached to this budget.",
        )

    file_path = (
        BACKEND_DIR / budget.approval_copy_path
    ).resolve()

    allowed_directory = BUDGET_APPROVAL_COPY_DIR.resolve()

    if not file_path.is_relative_to(allowed_directory):
        logger.error(
            "Invalid approval copy path for budget %s.",
            budget_id,
        )
        raise HTTPException(
            status_code=400,
            detail="Invalid approval copy path.",
        )

    if not file_path.is_file():
        raise HTTPException(
            status_code=404,
            detail="Budget approval copy file not found.",
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
            status_code=415,
            detail="Unsupported approval copy format.",
        )

    return FileResponse(
        path=file_path,
        media_type=media_type,
        filename=f"Budget_Approval_Copy{extension}",
        content_disposition_type="inline",
    )


# ---------------------------------------------------------
# GET ACTIVE BUDGET
# ---------------------------------------------------------

@router.get("/{budget_id}", response_model=BudgetResponse)
def get_budget(
    budget_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(
        require_roles("ADMIN", "ACCOUNTS", "IT_HEAD")
    ),
):

    budget = db.get(Budget, budget_id)

    if not budget:
        raise HTTPException(
            status_code=404,
            detail="Budget not found.",
        )

    return budget

# ---------------------------------------------------------
# SUBMIT BUDGET UPDATE APPROVAL REQUEST
# CAPEX ONLY
# ---------------------------------------------------------

@router.patch(
    "/{budget_id}",
    response_model=BudgetApprovalRequestResponse,
)
def update_budget(
    budget_id: int,
    payload: BudgetUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("ADMIN", "ACCOUNTS")),
):

    budget = db.get(Budget, budget_id)

    if not budget:
        raise HTTPException(
            status_code=404,
            detail="Budget not found.",
        )

    if budget.budget_type == "OPEX":
        raise HTTPException(
            status_code=422,
            detail=(
                "OPEX parent budgets cannot be updated directly. "
                "Submit an OPEX subcategory allocation request."
            ),
        )

    pending = db.query(BudgetApprovalRequest).filter(
        BudgetApprovalRequest.budget_id == budget_id,
        BudgetApprovalRequest.request_type == "UPDATE",
        BudgetApprovalRequest.status == "PENDING",
    ).first()

    if pending:
        raise HTTPException(
            status_code=409,
            detail="An update request for this budget is already pending approval.",
        )

    changes = payload.model_dump(exclude_unset=True)

    if not changes:
        raise HTTPException(
            status_code=400,
            detail="No fields provided.",
        )

    planned = changes.get(
        "planned_amount",
        budget.planned_amount,
    )

    if planned is None:
        raise HTTPException(
            status_code=422,
            detail="Planned amount cannot be null.",
        )

    planned = Decimal(str(planned))

    if planned < 0:
        raise HTTPException(
            status_code=422,
            detail="Planned amount cannot be negative.",
        )

    raw_token, token_hash, expires_at = generate_approval_token()

    request = BudgetApprovalRequest(
        budget_id=budget.id,
        request_type="UPDATE",
        status="PENDING",
        name=budget.name,
        financial_year=budget.financial_year,
        budget_type=budget.budget_type,
        planned_amount=planned,
        approved_amount=None,
        requested_by_id=current_user.id,
        approval_token_hash=token_hash,
        approval_token_expires_at=expires_at,
    )

    db.add(request)

    try:
        db.commit()
        db.refresh(request)

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Budget approval request violates a database constraint.",
        )

    notify_it_head(request, raw_token)

    return request


# ---------------------------------------------------------
# REQUESTER: LIST OWN APPROVAL REQUESTS
# ---------------------------------------------------------

@router.get(
    "/approval-requests/mine",
    response_model=list[BudgetApprovalRequestResponse],
)
def list_my_approval_requests(
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("ADMIN", "ACCOUNTS")),
):

    return db.query(BudgetApprovalRequest).filter(
        BudgetApprovalRequest.requested_by_id == current_user.id,
    ).order_by(
        BudgetApprovalRequest.requested_at.desc(),
    ).all()


# ---------------------------------------------------------
# EMAIL APPROVAL REVIEW PAGE
# ---------------------------------------------------------

@router.get(
    "/email-approval/{token}",
    response_class=HTMLResponse,
)
def email_approval_page(
    token: str,
    db: Session = Depends(get_db),
):

    request = validate_email_approval_token(token, db)

    request_id = request.id
    budget_name = escape(request.name)
    request_type = escape(request.request_type)
    financial_year = escape(request.financial_year)
    budget_type = escape(request.budget_type)
    planned_amount = escape(str(request.planned_amount))
    safe_token = escape(token, quote=True)

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>Budget Approval</title>

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
            }}
        </style>
    </head>

    <body>
        <div class="container">
            <h2>Budget Approval Request</h2>
            <p>Please review the request and decide the approved amount.</p>

            <table>
                <tr><td>Request ID</td><td>{request_id}</td></tr>
                <tr><td>Request Type</td><td>{request_type}</td></tr>
                <tr><td>Budget Name</td><td>{budget_name}</td></tr>
                <tr><td>Financial Year</td><td>{financial_year}</td></tr>
                <tr><td>Budget Type</td><td>{budget_type}</td></tr>
                <tr><td>Planned Amount</td><td>{planned_amount}</td></tr>
            </table>

            <label for="approved_amount">
                Approved Amount (IT Head)
            </label>

            <input
                id="approved_amount"
                type="number"
                min="0.01"
                max="{planned_amount}"
                step="0.01"
                value="{planned_amount}"
                required
            >

            <label for="remarks">Remarks (optional)</label>

            <textarea
                id="remarks"
                maxlength="2000"
                placeholder="Enter approval or rejection remarks">
            </textarea>

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
                const remarks = document.getElementById("remarks").value;
                const approvedInput = document.getElementById("approved_amount");
                const approvedAmount = approvedInput.value;

                if (action === "reject" &&
                    !confirm("Are you sure you want to reject this budget?")) {{
                    return;
                }}

                if (action === "approve") {{
                    if (approvedAmount === "") {{
                        result.textContent = "Please enter the approved amount.";
                        return;
                    }}

                    if (Number(approvedAmount) <= 0 ||
                        Number(approvedAmount) > Number("{planned_amount}")) {{
                        result.textContent =
                            "Approved amount must be greater than zero and cannot exceed the planned amount.";
                        return;
                    }}

                    if (!confirm("Approve this budget request with the entered amount?")) {{
                        return;
                    }}
                }}

                result.textContent = "Processing decision...";

                const body = {{
                    remarks: remarks
                }};

                if (action === "approve") {{
                    body.approved_amount = approvedAmount;
                }}

                try {{
                    const response = await fetch(
                        `/api/budgets/email-approval/${{token}}/${{action}}`,
                        {{
                            method: "POST",
                            headers: {{
                                "Content-Type": "application/json"
                            }},
                            body: JSON.stringify(body)
                        }}
                    );

                    const data = await response.json();

                    if (!response.ok) {{
                        throw new Error(
                            data.detail || "Unable to process decision."
                        );
                    }}

                    result.textContent =
                        action === "approve"
                        ? "Budget approved successfully."
                        : "Budget rejected successfully.";

                    document.querySelectorAll("button").forEach(
                        button => button.disabled = true
                    );

                }} catch (error) {{
                    result.textContent = error.message;
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

def process_email_decision(
    token: str,
    decision: str,
    payload: BudgetApprovalDecision,
    db: Session,
):

    request = validate_email_approval_token(token, db)

    budget = None

    if decision == "approve":

        approved_amount = validate_approved_amount(
            payload.approved_amount,
            request.planned_amount,
        )

        if request.request_type == "CREATE":

            existing = db.query(Budget).filter(
                Budget.name == request.name,
                Budget.financial_year == request.financial_year,
                Budget.budget_type == request.budget_type,
            ).first()

            if existing:
                raise HTTPException(
                    status_code=409,
                    detail="An active budget with these details already exists.",
                )

            budget = Budget(
    name=request.name,
    financial_year=request.financial_year,
    budget_type=request.budget_type,
    planned_amount=request.planned_amount,
    approved_amount=approved_amount,
    approval_copy_path=request.approval_copy_path,
)

            db.add(budget)

        elif request.request_type == "UPDATE":

            budget = db.get(Budget, request.budget_id)

            if not budget:
                raise HTTPException(
                    status_code=404,
                    detail="The budget associated with this request no longer exists.",
                )

            budget.planned_amount = request.planned_amount
            budget.approved_amount = approved_amount

        else:
            raise HTTPException(
                status_code=422,
                detail="Unsupported approval request type.",
            )

        request.approved_amount = approved_amount
        request.status = "APPROVED"

    elif decision == "reject":

        request.status = "REJECTED"

    else:
        raise HTTPException(
            status_code=422,
            detail="Unsupported decision.",
        )

    request.decided_by_id = None
    request.decided_at = datetime.utcnow()
    request.remarks = payload.remarks

    invalidate_approval_token(request)

    try:
        db.commit()

        if budget is not None:
            db.refresh(budget)

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Could not save the approval decision.",
        )

    # Accounts notification happens only after a successful commit.
    if decision == "approve" and budget is not None:
        notify_accounts_after_budget_approval(
            request=request,
            budget=budget,
        )

        return {
            "message": "Budget approved successfully.",
            "budget_id": budget.id,
            "approved_amount": str(budget.approved_amount),
        }

    return {
        "message": "Budget rejected successfully.",
        "request_id": request.id,
    }


# ---------------------------------------------------------
# EMAIL APPROVE
# ---------------------------------------------------------

@router.post("/email-approval/{token}/approve")
def approve_budget_by_email(
    token: str,
    payload: BudgetApprovalDecision,
    db: Session = Depends(get_db),
):

    return process_email_decision(
        token=token,
        decision="approve",
        payload=payload,
        db=db,
    )


# ---------------------------------------------------------
# EMAIL REJECT
# ---------------------------------------------------------

@router.post("/email-approval/{token}/reject")
def reject_budget_by_email(
    token: str,
    payload: BudgetApprovalDecision,
    db: Session = Depends(get_db),
):

    return process_email_decision(
        token=token,
        decision="reject",
        payload=payload,
        db=db,
    )


# ---------------------------------------------------------
# LIST PENDING APPROVAL REQUESTS
# IT HEAD ONLY
# ---------------------------------------------------------

@router.get(
    "/approval-requests/pending",
    response_model=list[BudgetApprovalRequestResponse],
)
def list_pending_approval_requests(
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("IT_HEAD")),
):

    return db.query(BudgetApprovalRequest).filter(
        BudgetApprovalRequest.status == "PENDING",
    ).order_by(
        BudgetApprovalRequest.requested_at.asc(),
    ).all()


# ---------------------------------------------------------
# APPROVE BUDGET REQUEST
# IT HEAD ONLY
# ---------------------------------------------------------

@router.post(
    "/approval-requests/{request_id}/approve",
    response_model=BudgetResponse,
)
def approve_budget_request(
    request_id: int,
    payload: BudgetApprovalDecision,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("IT_HEAD")),
):

    request = db.get(BudgetApprovalRequest, request_id)

    if not request:
        raise HTTPException(
            status_code=404,
            detail="Approval request not found.",
        )

    ensure_request_pending(request)

    approved_amount = validate_approved_amount(
        payload.approved_amount,
        request.planned_amount,
    )

    if request.request_type == "CREATE":

        existing = db.query(Budget).filter(
            Budget.name == request.name,
            Budget.financial_year == request.financial_year,
            Budget.budget_type == request.budget_type,
        ).first()

        if existing:
            raise HTTPException(
                status_code=409,
                detail="An active budget with these details already exists.",
            )

        budget = Budget(
    name=request.name,
    financial_year=request.financial_year,
    budget_type=request.budget_type,
    planned_amount=request.planned_amount,
    approved_amount=approved_amount,
    approval_copy_path=request.approval_copy_path,
)

        db.add(budget)

    elif request.request_type == "UPDATE":

        budget = db.get(Budget, request.budget_id)

        if not budget:
            raise HTTPException(
                status_code=404,
                detail="The budget associated with this request no longer exists.",
            )

        budget.planned_amount = request.planned_amount
        budget.approved_amount = approved_amount

    else:
        raise HTTPException(
            status_code=422,
            detail="Unsupported approval request type.",
        )

    request.approved_amount = approved_amount
    request.status = "APPROVED"
    request.decided_by_id = current_user.id
    request.decided_at = datetime.utcnow()
    request.remarks = payload.remarks

    invalidate_approval_token(request)

    try:
        db.commit()
        db.refresh(budget)

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Approved budget violates a database constraint.",
        )

    # Notify Accounts only after the approval is committed.
    notify_accounts_after_budget_approval(
        request=request,
        budget=budget,
    )

    return budget


# ---------------------------------------------------------
# REJECT BUDGET REQUEST
# IT HEAD ONLY
# ---------------------------------------------------------

@router.post(
    "/approval-requests/{request_id}/reject",
    response_model=BudgetApprovalRequestResponse,
)
def reject_budget_request(
    request_id: int,
    payload: BudgetApprovalDecision,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("IT_HEAD")),
):

    request = db.get(BudgetApprovalRequest, request_id)

    if not request:
        raise HTTPException(
            status_code=404,
            detail="Approval request not found.",
        )

    ensure_request_pending(request)

    request.status = "REJECTED"
    request.decided_by_id = current_user.id
    request.decided_at = datetime.utcnow()
    request.remarks = payload.remarks

    invalidate_approval_token(request)

    try:
        db.commit()
        db.refresh(request)

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Could not reject the approval request.",
        )

    return request
