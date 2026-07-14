// Bundle entry: mounts CaddieOS and shims window.storage over localStorage so the
// standalone build behaves exactly like the Claude artifact runtime.
import React from "react";
import { createRoot } from "react-dom/client";
import CaddieOS from "../src/CaddieOS.jsx";

if (!window.storage) {
  window.storage = {
    get: async (k) => { try { const v = localStorage.getItem(k); return v != null ? { value: v } : null; } catch (e) { return null; } },
    set: async (k, v) => { try { localStorage.setItem(k, v); } catch (e) {} }
  };
}

const el = document.getElementById("root");
el.textContent = "";
createRoot(el).render(React.createElement(CaddieOS));
