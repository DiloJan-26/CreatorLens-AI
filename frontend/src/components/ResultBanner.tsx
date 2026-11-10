import type { ReactNode } from "react";
import { Icon } from "./ui";

export function ResultBanner({
  title,
  description,
  winner = false,
  detail,
}: {
  title: string;
  description: string;
  winner?: boolean;
  detail?: ReactNode;
}) {
  return (
    <div className={`result-banner ${winner ? "result-winner" : ""}`}>
      <span className="result-symbol">
        <Icon name={winner ? "trophy" : "shield"} size={27} />
      </span>
      <div className="result-copy">
        <h2>{title}</h2>
        <p>{description}</p>
      </div>
      {detail && <div className="result-detail">{detail}</div>}
    </div>
  );
}
