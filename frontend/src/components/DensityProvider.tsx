import { createContext, useContext, useEffect } from 'react';
import { useStore, type Density } from '../store';

const DENSITY_KEY = 'rt-density';

/** Write (or remove) the density attribute on `<html>`. `comfortable` removes
 *  it rather than setting it to a value, so the CSS only ever matches the one
 *  non-default state. Exported for the density tests. */
export function applyDensity(root: HTMLElement, density: Density) {
  if (density === 'compact') {
    root.dataset.density = 'compact';
  } else {
    delete root.dataset.density;
  }
}

const DensityContext = createContext<{ density: Density; setDensity: (d: Density) => void }>({
  density: 'comfortable',
  setDensity: () => {},
});

export function useDensity() {
  return useContext(DensityContext);
}

export function DensityProvider({ children }: { children: React.ReactNode }) {
  const density = useStore((s) => s.density);
  const setDensity = useStore((s) => s.setDensity);

  useEffect(() => {
    applyDensity(document.documentElement, density);
    try {
      localStorage.setItem(DENSITY_KEY, density);
    } catch {
      // localStorage unavailable (private-browsing edge cases) — density still
      // applies for this session, it just won't survive a reload.
    }
  }, [density]);

  return <DensityContext.Provider value={{ density, setDensity }}>{children}</DensityContext.Provider>;
}
