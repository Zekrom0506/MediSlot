// Turn API errors into messages written for patients and staff.
export function friendlyErrorMessage(error) {
  if (!error) {
    return "";
  }
  if (error.code === "SLOT_ALREADY_BOOKED") {
    return "Sorry, this slot was just booked. Please choose another slot.";
  }
  if (error.code === "RATE_LIMITED") {
    const seconds = error.retryAfterSeconds;
    if (seconds) {
      return `Too many attempts. Please wait ${seconds} seconds and try again.`;
    }
    return "Too many attempts. Please wait a minute and try again.";
  }
  if (error.code === "TOKEN_EXPIRED") {
    return "Your session has expired. Please log in again.";
  }
  return error.message || "Something went wrong. Please try again.";
}
