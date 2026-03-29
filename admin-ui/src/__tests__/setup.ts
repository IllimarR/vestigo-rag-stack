import "@testing-library/jest-dom";

// jsdom's localStorage exists but isn't a real Storage instance — the
// implementation returned by `window.localStorage` doesn't accept
// per-test cleanup well. Replace with a simple in-memory store so
// `beforeEach` can wipe state cleanly.

class MemoryStorage {
  private store = new Map<string, string>();
  get length(): number {
    return this.store.size;
  }
  key(index: number): string | null {
    return Array.from(this.store.keys())[index] ?? null;
  }
  getItem(key: string): string | null {
    return this.store.get(key) ?? null;
  }
  setItem(key: string, value: string): void {
    this.store.set(key, String(value));
  }
  removeItem(key: string): void {
    this.store.delete(key);
  }
  clear(): void {
    this.store.clear();
  }
}

Object.defineProperty(window, "localStorage", {
  value: new MemoryStorage(),
  writable: false,
});
