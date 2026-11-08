import Link from "next/link";
import taxonomy from "@/lib/taxonomy.json";
import { Mosaic } from "@/components/Mosaic";

export default function Home() {
  const subs = taxonomy.narratives.reduce((a, n) => a + n.subnarratives.length, 0);
  return (
    <div className="rise">
      <section className="hero">
        <div className="copy">
          <h1 className="display">
            Forward it.
            <br />
            Your bot <i className="hl hl-draw">answers.</i>
          </h1>
          <p className="lede">
            Build a Telegram bot that recognizes the propaganda narrative inside a message and replies with the response you wrote in advance.
          </p>
          <div className="row">
            <Link href="/new" className="btn solid">
              Create a bot <span aria-hidden="true">→</span>
            </Link>
            <Link href="/bots" className="btn">
              My bots
            </Link>
          </div>
        </div>
        <figure className="proof" style={{ margin: 0 }} aria-label="Example: a forwarded message, what the classifier found, and the bot’s reply">
          <span className="stamp">example</span>
          <p className="msg" lang="ru">
            НАТО спровоцировало эту войну, Россия лишь <span className="mk">защищает себя</span>.
          </p>
          <p className="note">
            <span>Found:</span> <b>Russia is the Victim</b> <span aria-hidden="true">›</span> <b>only self-defence</b> <span className="num">0.82</span>
          </p>
          <div className="reply">
            <small>Your bot replies</small>
            <p lang="ru">Утверждения о «провокации НАТО» — частый приём.</p>
          </div>
        </figure>
      </section>

      <section className="sec" aria-labelledby="how">
        <h2 className="h2" id="how">
          What you decide
        </h2>
        <p className="lead">The classifier is shared. Everything the bot says is yours.</p>
        <div className="cols3">
          <div>
            <h3 className="h3">Which narratives get a reply</h3>
            <p>Write one response per narrative, or a different one for a specific sub-narrative.</p>
          </div>
          <div>
            <h3 className="h3">How sure it must be</h3>
            <p>The confidence threshold sets how strong a match has to be before the bot answers.</p>
          </div>
          <div>
            <h3 className="h3">What to say when nothing fits</h3>
            <p>A fallback reply covers messages with no known narrative, so the bot never goes silent.</p>
          </div>
        </div>
      </section>

      <section className="sec" aria-labelledby="map">
        <h2 className="h2" id="map">
          The {taxonomy.narratives.length} narratives it can recognize
        </h2>
        <p className="lead">
          From the SemEval 2025 Task 10 taxonomy: {subs} sub-narratives across Russian-language messages about the war in Ukraine. Tile size follows the number of sub-narratives.
        </p>
        <Mosaic narratives={taxonomy.narratives} />
        <div className="row" style={{ marginTop: 32 }}>
          <Link href="/new" className="btn solid">
            Create a bot <span aria-hidden="true">→</span>
          </Link>
        </div>
      </section>
    </div>
  );
}
