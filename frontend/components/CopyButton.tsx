"use client";

import { useState } from "react";

/** Green copy button — copies the given text to the clipboard on click. */
export default function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      // Fallback for older browsers / non-secure contexts.
      const ta = document.createElement("textarea");
      ta.value = text;
      ta.style.position = "fixed";
      ta.style.opacity = "0";
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      document.body.removeChild(ta);
    }
    setCopied(true);
    window.setTimeout(() => setCopied(false), 2000);
  }

  return (
    <button
      type="button"
      className={`copy-btn ${copied ? "copy-btn--done" : ""}`}
      onClick={handleCopy}
      aria-label="Copy title and content"
    >
      <span className="copy-btn__icon" aria-hidden="true">
        {copied ? "✓" : "⧉"}
      </span>
      {copied ? "Copied!" : "Copy"}
    </button>
  );
}
