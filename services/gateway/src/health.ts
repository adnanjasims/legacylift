export interface HealthBody {
  status: "ok";
  service: "gateway";
}

/**
 * JSON body for GET /health and GET /ready in M0.
 * Downstream auth and proxy checks start in M3.
 */
export function healthPayload(): HealthBody {
  return { status: "ok", service: "gateway" };
}
