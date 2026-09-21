// The web app's transport reads `process.env.NEXT_PUBLIC_API_URL` behind a `typeof process`
// guard. There is no Node here; declare the name so the shared file typechecks in this package.
declare var process: { env: Record<string, string | undefined> } | undefined;
