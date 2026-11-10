"use client";

import { useId } from "react";
import { Icon } from "./ui";

/** Small local brand glyphs; labels always remain visible beside them. */
export function PlatformIcon({
  platform,
  size = 20,
}: {
  platform: string;
  size?: number;
}) {
  const gradient = useId();
  const name = platform.toLowerCase();
  if (name === "youtube")
    return (
      <svg
        width={size}
        height={size}
        viewBox="0 0 24 24"
        aria-hidden="true"
        className="platform-icon"
      >
        <rect x="1" y="4" width="22" height="16" rx="5" fill="#FF0033" />
        <path d="m10 8 7 4-7 4Z" fill="white" />
      </svg>
    );
  if (name === "facebook")
    return (
      <svg
        width={size}
        height={size}
        viewBox="0 0 24 24"
        aria-hidden="true"
        className="platform-icon"
      >
        <circle cx="12" cy="12" r="11" fill="#0866FF" />
        <path
          d="M13.5 22v-8h2.7l.4-3h-3.1V9.2c0-.9.3-1.5 1.6-1.5h1.7V5.1c-.3 0-1.3-.1-2.4-.1-2.4 0-4 1.5-4 4.2V11H8v3h2.4v8Z"
          fill="white"
        />
      </svg>
    );
  if (name === "instagram")
    return (
      <svg
        width={size}
        height={size}
        viewBox="0 0 24 24"
        aria-hidden="true"
        className="platform-icon"
      >
        <defs>
          <linearGradient id={gradient} x1="0" y1="1" x2="1" y2="0">
            <stop stopColor="#FFB344" />
            <stop offset=".45" stopColor="#E43470" />
            <stop offset="1" stopColor="#7554C9" />
          </linearGradient>
        </defs>
        <rect
          x="1"
          y="1"
          width="22"
          height="22"
          rx="6"
          fill={`url(#${gradient})`}
        />
        <rect
          x="5.2"
          y="5.2"
          width="13.6"
          height="13.6"
          rx="4"
          fill="none"
          stroke="white"
          strokeWidth="1.7"
        />
        <circle
          cx="12"
          cy="12"
          r="3.3"
          fill="none"
          stroke="white"
          strokeWidth="1.7"
        />
        <circle cx="16.7" cy="7.5" r="1" fill="white" />
      </svg>
    );
  return <Icon name="globe" size={size} />;
}
