import { cn } from "../../lib/utils.js";
import { avatarColorOf, avatarTextOf, getCustomAgent } from "../../lib/agent-custom.js";

/**
 * Agent 头像：优先自定义图片，否则颜色块 + 文字。
 * @stable
 */
export function AgentAvatar({ file, name, index = 0, size = "md", className }) {
  const custom = getCustomAgent(file);
  const sizeCls = {
    sm: "size-6 text-[11px] rounded-md",
    md: "size-7 text-xs rounded-lg",
    lg: "size-10 text-base rounded-lg",
  }[size] || "size-7 text-xs rounded-lg";

  return (
    <span
      className={cn(
        "grid shrink-0 place-items-center overflow-hidden font-semibold text-white",
        sizeCls,
        className,
      )}
      style={{ background: avatarColorOf(file, index) }}
      aria-hidden="true"
    >
      {custom?.avatarImage ? (
        <img
          src={custom.avatarImage}
          alt=""
          className="size-full object-cover"
          draggable={false}
        />
      ) : (
        avatarTextOf({ file, name }, index)
      )}
    </span>
  );
}
