import { Link } from 'react-router-dom'
import { ArrowRight, BookOpen } from 'lucide-react'
import { tutorialSections, type TutorialSection } from '../content/tutorialContent'

/** 文件名 → 指纹化 URL（import.meta.glob 编译期展开，文件缺失即无该键，分节渲染时自然跳过） */
const tutorialImages: Record<string, string> = {}
for (const [path, url] of Object.entries(
  import.meta.glob('../assets/tutorial/*.png', { query: '?url', import: 'default', eager: true }) as Record<string, string>,
)) {
  const file = path.split('/').pop()
  if (file) tutorialImages[file] = url
}

function Section({ section }: { section: TutorialSection }) {
  const links = section.links ?? []
  return (
    <section id={section.id} className="panel" style={{ marginTop: 18, scrollMarginTop: 20 }}>
      <div className="panel-head">
        <h6 className="panel-title">
          <span className="kicker" />
          {section.title}
        </h6>
      </div>
      <div className="panel-body" style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        {section.paragraphs.map((p, i) => (
          <p key={i} style={{ margin: 0, lineHeight: 1.75, maxWidth: 860 }}>
            {p}
          </p>
        ))}
        {section.images?.map(
          (img) =>
            tutorialImages[img.file] && (
              <figure key={img.file} style={{ margin: '6px 0 0' }}>
                <img
                  src={tutorialImages[img.file]}
                  alt={img.caption ?? section.title}
                  loading="lazy"
                  style={{ width: '100%', maxWidth: 980, borderRadius: 10, border: '1px solid var(--border, rgba(128,128,128,0.2))' }}
                />
                {img.caption && (
                  <figcaption className="text-sm opacity-75" style={{ marginTop: 6 }}>
                    {img.caption}
                  </figcaption>
                )}
              </figure>
            ),
        )}
        {links.length > 0 && (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 4, alignItems: 'center' }}>
            <span className="text-sm opacity-75">前往：</span>
            {links.map((l) => (
              <Link key={l.to + l.label} className="btn btn-outline-secondary btn-sm" to={l.to}>
                {l.label} <ArrowRight size={12} style={{ verticalAlign: -2 }} />
              </Link>
            ))}
          </div>
        )}
      </div>
    </section>
  )
}

export default function TutorialPage() {
  const jump = (id: string) => {
    document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }
  return (
    <div>
      <div className="hero">
        <h1>
          <BookOpen size={26} style={{ verticalAlign: -4, marginRight: 10 }} aria-hidden />
          使用教程
        </h1>
        <p>十分钟了解每个页面能做什么、怎么用。第一次使用请先看「五分钟上手路径」。</p>
      </div>

      <nav className="seg" aria-label="教程目录" style={{ marginTop: 16, flexWrap: 'wrap' }}>
        {tutorialSections.map((s) => (
          <button key={s.id} type="button" className="seg-item" onClick={() => jump(s.id)}>
            {s.title}
          </button>
        ))}
      </nav>

      {tutorialSections.map((s) => (
        <Section key={s.id} section={s} />
      ))}

      <p className="text-sm opacity-60" style={{ marginTop: 20 }}>
        截图与界面如有出入，以实际页面为准；界面改版后替换 src/assets/tutorial/ 下同名图片并重新构建即可更新教程。
      </p>
    </div>
  )
}
