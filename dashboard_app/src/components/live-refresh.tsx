"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

export function LiveRefresh({ seconds }: { seconds: number }) {
  const router = useRouter();

  useEffect(() => {
    const interval = window.setInterval(() => {
      router.refresh();
    }, seconds * 1000);

    return () => {
      window.clearInterval(interval);
    };
  }, [router, seconds]);

  return null;
}
