import type { Taxonomy } from "@/types/api";

// Column x row spans on a 6-column grid. Sizes follow how many sub-narratives each narrative has;
// every row of the grid sums to 6 columns, so it closes with no gaps. Keyed by narrative position.
const SPAN: [number, number][] = [[3, 1], [3, 2], [3, 1], [2, 1], [2, 1], [2, 1], [3, 1], [2, 1], [1, 1], [3, 1], [3, 1]];
const TONE = ["t2", "t0", "t3", "t1", "t3", "t2", "t0", "t3", "t2", "t3", "t1"];

interface Props {
  narratives: Taxonomy["narratives"];
  /** Builder mode: tiles are buttons, answered ones fill with ink. */
  answered?: Set<number>;
  picked?: number | null;
  onPick?: (i: number) => void;
}

export function Mosaic({ narratives, answered, picked, onPick }: Props) {
  return (
    <div className="mosaic" role={onPick ? "group" : "list"} aria-label="The narratives a bot can answer">
      {narratives.map((n, i) => {
        const [c, r] = SPAN[i] ?? [1, 1];
        const style = { gridColumn: `span ${c}`, gridRow: `span ${r}` };
        const count = n.subnarratives.length;
        const inner = (
          <>
            <b>{n.name}</b>
            <span>{count ? `${count} sub-narratives` : "narrative only"}</span>
          </>
        );
        if (!onPick) {
          return (
            <div key={n.name} role="listitem" className={"tile " + TONE[i % TONE.length]} style={style}>
              {inner}
            </div>
          );
        }
        const done = answered?.has(i);
        return (
          <button
            key={n.name}
            type="button"
            aria-pressed={picked === i}
            aria-label={`${n.name}: ${done ? "has a reply" : "no reply yet"}`}
            className={"tile " + (done ? "t0" : "t3")}
            style={style}
            onClick={() => onPick(i)}
          >
            {inner}
          </button>
        );
      })}
    </div>
  );
}
