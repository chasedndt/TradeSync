/// <reference types="vite/client" />

// No build-time variable carries a credential: every value Vite inlines is in the
// bundle served to anyone who can load the Cockpit. Credentials are entered in
// Settings and kept for the browser session (src/api/credentials.ts).
