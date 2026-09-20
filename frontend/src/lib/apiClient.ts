import api from "./api";

// Re-export of the single configured axios instance. Kept as a named export
// because four feature repositories import `{ apiClient }` from this path.
export const apiClient = api;
