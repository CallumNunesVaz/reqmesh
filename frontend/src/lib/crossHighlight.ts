// Cross-highlighting mappings between requirements and the components that
// satisfy them. The shared hovered-entity state is just `{ kind, id }`; these
// pure helpers turn that into the sets of ids the other list / the canvas must
// light up, so the mapping logic is unit-testable rather than buried in a
// component.

/** Components that directly satisfy a requirement. */
export function componentsSatisfyingRequirement(
  reqId: string,
  components: { id: string; satisfies: string[] }[],
): string[] {
  const out: string[] = [];
  for (const c of components) {
    if (c.satisfies.includes(reqId)) out.push(c.id);
  }
  return out;
}

/** Requirements a component directly satisfies. */
export function requirementsSatisfiedByComponent(
  componentId: string,
  components: { id: string; satisfies: string[] }[],
): string[] {
  const c = components.find((comp) => comp.id === componentId);
  return c ? [...c.satisfies] : [];
}
