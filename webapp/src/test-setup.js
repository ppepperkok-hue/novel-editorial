import "@testing-library/jest-dom/vitest";

window.matchMedia =
  window.matchMedia ||
  (() => ({
    matches: false,
    addEventListener: () => {},
    removeEventListener: () => {},
    addListener: () => {},
    removeListener: () => {},
  }));

global.ResizeObserver =
  global.ResizeObserver ||
  class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
