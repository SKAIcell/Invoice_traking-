
type CompanyLogoProps = {
  className?: string;
};

export default function CompanyLogo({
  className = "",
}: CompanyLogoProps) {
  return (
    <img
      src="/images/skipper-logo.jpg"
      alt="Skipper Limited"
      className={`company-logo ${className}`}
    />
  );
}
