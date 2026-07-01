"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

export function SearchBar() {
  const [value, setValue] = useState("");
  const router = useRouter();

  function go(e: React.FormEvent) {
    e.preventDefault();
    if (value.trim()) router.push(`/stock/${value.trim().toUpperCase()}`);
  }

  return (
    <form onSubmit={go} className="flex w-full max-w-sm gap-2">
      <input
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder="Search ticker (e.g. AAPL)"
        className="flex-1 rounded-md border border-gray-300 bg-white px-3 py-2 text-sm outline-none focus:border-brand"
      />
      <button type="submit" className="rounded-md bg-brand px-4 py-2 text-sm font-semibold text-white hover:bg-brand-dark">
        Go
      </button>
    </form>
  );
}
