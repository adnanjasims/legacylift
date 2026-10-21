import { buildApp } from "./app.js";

/**
 * Bind the gateway HTTP server using HOST and PORT from the environment.
 * HOST defaults to 127.0.0.1. Compose sets HOST=0.0.0.0 so the container
 * is reachable on the published port.
 */
async function main(): Promise<void> {
  const app = buildApp();
  const port = Number(process.env.PORT ?? 3000);
  const host = process.env.HOST ?? "127.0.0.1";
  await app.listen({ port, host });
}

main().catch((err: unknown) => {
  console.error(err);
  process.exit(1);
});
