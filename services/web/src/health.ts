export interface HealthBody {
  status: "ok";
  service: "web";
}

/**
 * JSON body for GET /health and GET /ready on the Vite server.
 */
export function healthPayload(): HealthBody {
  return { status: "ok", service: "web" };
}
