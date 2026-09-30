import { generatePath } from "react-router";

// The route of a claim's page, and the link to one claim's page.
export const CLAIM_PAGE = "/claims/:claimId";
export const claimPage = (claimId: string) =>
  generatePath(CLAIM_PAGE, { claimId });
