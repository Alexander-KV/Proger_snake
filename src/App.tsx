import { useRef, useState } from 'react'
import './App.css'

const sections = [
  { title: 'Создать матч', description: 'Собери команды. Задай условия. Начни игру.', detail: 'Здесь появятся настройки поля, выбор команд и запуск соревнования.' },
  { title: 'Матчи', description: 'Следи за игрой алгоритмов на арене.', detail: 'Здесь появятся список матчей, просмотр игрового поля и результаты.' },
  { title: 'Редактор алгоритма', description: 'Преврати свою стратегию в код.', detail: 'Здесь появятся редактор кода, выбор языка и отправка алгоритма на матч.' },
  { title: 'Команды', description: 'Объединяйся, чтобы побеждать.', detail: 'Здесь появятся создание команды, список участников и алгоритм змейки.' },
  { title: 'Правила', description: 'Узнай, как устроено соревнование.', detail: 'Здесь появятся согласованные правила движения, столкновений и определения победителя.' },
]

function ArenaVisual() {
  return (
    <div className="arena-visual" aria-hidden="true">
      <div className="arena-haze" />
      <div className="arena-plane">
        <svg viewBox="0 0 640 520" fill="none">
          <defs>
            <pattern id="grid" width="32" height="32" patternUnits="userSpaceOnUse">
              <path d="M 32 0 H 0 V 32" stroke="currentColor" strokeWidth="0.7" />
            </pattern>
          </defs>
          <rect width="640" height="520" fill="url(#grid)" className="arena-grid" />
          <path className="snake snake-dark" pathLength="100" d="M64 352 V224 H288 V416 H544 V352 Z" />
          <path className="snake snake-red" pathLength="100" d="M64 416 V288 H224 V128 H416 V320 H544 V448 H224 V416 Z" />
          <g className="food">
            <rect x="311" y="279" width="18" height="18" />
          </g>
        </svg>
      </div>
    </div>
  )
}

function App() {
  const [activeSection, setActiveSection] = useState<number | null>(null)
  const headingRef = useRef<HTMLHeadingElement>(null)
  const buttonRefs = useRef<(HTMLButtonElement | null)[]>([])
  const selected = activeSection === null ? null : sections[activeSection]

  function openSection(index: number) {
    setActiveSection(index)
    requestAnimationFrame(() => headingRef.current?.focus())
  }

  function returnToMenu() {
    const previous = activeSection
    setActiveSection(null)
    requestAnimationFrame(() => {
      if (previous !== null) buttonRefs.current[previous]?.focus()
    })
  }

  return (
    <div className="app-shell">
      <header className="site-header flex items-center justify-between">
        <a className="brand flex items-center gap-3" href="#main" aria-label="Snake Arena — к главному экрану">
          <svg width="25" height="25" viewBox="0 0 25 25" fill="none" aria-hidden="true">
            <path d="M3 21V4H14V12H22V21H11V13" stroke="currentColor" strokeWidth="3" />
          </svg>
          <span>SNAKE ARENA<span className="brand-dot text-accent">.</span></span>
        </a>
        <span className="header-caption">СОРЕВНОВАНИЯ АЛГОРИТМОВ</span>
      </header>

      <main id="main" className="main-layout">
        <section className="hero" aria-labelledby="hero-title">
          <div className="hero-copy">
            <h1 id="hero-title">SNAKE<br /><span>ARENA</span><span className="title-dot">.</span></h1>
            <p className="hero-slogan">Твой код. Твоя стратегия.<br /><span>Твоя арена.</span></p>
          </div>
          <ArenaVisual />
        </section>

        <section className="control-panel" aria-label="Управление ареной">
          {selected ? (
            <div className="placeholder">
              <p className="eyebrow text-accent">В РАЗРАБОТКЕ</p>
              <h2 ref={headingRef} tabIndex={-1}>{selected.title}</h2>
              <div className="fading-line" />
              <p className="placeholder-copy">{selected.detail}</p>
              <p className="placeholder-label">Пока это заглушка раздела.</p>
              <button className="fill-button back-button" onClick={returnToMenu}><span>← Главное меню</span></button>
            </div>
          ) : (
            <>
              <h2 className="panel-heading">Главное меню</h2>
              <nav aria-label="Главное меню">
                {sections.map((section, index) => (
                  <button key={section.title} ref={(element) => { buttonRefs.current[index] = element }} className={`menu-button fill-button ${index === 0 ? 'primary-button' : ''}`} onClick={() => openSection(index)}>
                    <span className="menu-number">0{index + 1}</span>
                    <span className="menu-copy"><span className="menu-title">{section.title}</span><span className="menu-description">{section.description}</span></span>
                    <span className="menu-arrow" aria-hidden="true">↗</span>
                  </button>
                ))}
              </nav>
            </>
          )}
        </section>
      </main>
    </div>
  )
}

export default App
