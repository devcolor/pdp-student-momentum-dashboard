import type { components, paths } from "./generated/schema";

/** Response and request shapes, generated from the server's OpenAPI schema by `bun run api-types`. */
export type Schemas = components["schemas"];

/** Every endpoint's parameters and responses, keyed by path. */
export type Paths = paths;
