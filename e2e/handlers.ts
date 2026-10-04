// The handlers the end-to-end tests sign in as, with the password the Auth
// stand-in signs every handler in with, and where each one's signed-in browser
// storage is kept for the tests.
export const TEST_PASSWORD = "e2e-handler-password";

export const HANDLERS = {
  dana: {
    handler_id: "HND-01",
    name: "Dana Whitfield",
    email: "dana.whitfield@undercover.example",
    storage: "e2e/.auth/dana.json",
  },
  marcus: {
    handler_id: "HND-02",
    name: "Marcus Oyelaran",
    email: "marcus.oyelaran@undercover.example",
    storage: "e2e/.auth/marcus.json",
  },
};
