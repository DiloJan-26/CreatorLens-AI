import Link from "next/link";
import {Icon} from "./ui";

export function AssistantLinkBar() {
  return <div className="insight-assistant-link">
    <span><Icon name="chat" size={20}/> Discuss your findings and explore alternative wording.</span>
    <Link href="/chat" className="button-primary">Ask the Assistant <Icon name="arrow" size={16}/></Link>
  </div>;
}
