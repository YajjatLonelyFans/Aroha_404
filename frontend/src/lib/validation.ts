// Basic format checks for form input. Each returns an error message, or null when valid.
// The backend validates again; these only give early, friendly feedback.

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[A-Za-z]{2,}$/;
const USERNAME_RE = /^[A-Za-z0-9._]{3,20}$/;

export function checkEmail(value: string): string | null {
  if (!value.trim()) return "Enter your email.";
  return EMAIL_RE.test(value.trim()) ? null : "Enter an email like name@example.com.";
}

export function checkUsername(value: string): string | null {
  if (!value.trim()) return "Choose a username.";
  return USERNAME_RE.test(value.trim()) ? null : "Use 3–20 letters, numbers, dots or underscores.";
}

export function checkPassword(value: string): string | null {
  if (!value) return "Enter a password.";
  if (value.length < 8) return "Use at least 8 characters.";
  if (!/[A-Za-z]/.test(value) || !/\d/.test(value)) return "Include at least one letter and one number.";
  return null;
}

/** Monthly electricity use in units (kWh); the backend accepts more than 0 and up to 20,000. */
export function checkMonthlyUnits(value: string): string | null {
  if (!value.trim()) return "Enter your monthly units.";
  const n = Number(value);
  if (!Number.isFinite(n) || n <= 0) return "Enter a number of units greater than 0.";
  if (n > 20000) return "That's more than a home usually uses. Check the units on your bill.";
  return null;
}
