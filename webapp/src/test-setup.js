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

if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => {};
}

class MockEventSource {
  constructor() {
    this.readyState = 0;
    this.onmessage = null;
  }
  close() {}
  addEventListener() {}
  removeEventListener() {}
}
global.EventSource = global.EventSource || MockEventSource;
