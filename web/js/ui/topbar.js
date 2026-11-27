import { esc } from "../format.js";
import { icon, glyph } from "./icon.js";
import { statDefs, fmtStat } from "./yieldReport.js";

// The national stats are buttons: each opens its report (ui/yieldReport.js, wired in main.js).
export function renderTopbar(nation) {
  const items = statDefs(nation).map((d) => {
    const ic = d.yield ? glyph(d.yield, 17) : icon(d.iconId, d.emoji, { size: 17 });
    const value = fmtStat(d, d.value);
    const tip = `${d.name}：${d.description} 点击查看报告。`;
    return `<button type="button" class="yield" data-report="${esc(d.key)}" aria-expanded="false" aria-haspopup="dialog" aria-controls="yield-report"
      title="${esc(tip)}" aria-label="${esc(d.name)}：${esc(value)}。打开报告">
      <span class="ico" style="color:${esc(d.color)}">${ic}</span><span style="color:${esc(d.color)}">${esc(value)}</span><span class="caret" aria-hidden="true"></span></button>`;
  });
  const el = document.getElementById("yields");
  el.innerHTML = items.join("");
  // When the bar is too narrow for every yield, the row scrolls on its own (search and buttons always fit);
  // a fade on the right edge shows there is more.
  const check = () => el.classList.toggle("clipped", el.scrollWidth > el.clientWidth + 1);
  if (typeof ResizeObserver === "function") new ResizeObserver(check).observe(el);
  check();
  document.getElementById("turn").innerHTML = `回合 <b>${esc(nation.year ?? "")}</b> · ${esc(nation.vintage || "")}`;
}
