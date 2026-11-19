export default function AlgorithmHelp() {
  return (
    <details className="algorithm-help">
      <summary>Справка по Python и правилам</summary>
      <p>
        <code>decide(state, memory)</code> получает снимок перед ходом. Верните
        словарь с <code>direction</code> из{' '}
        <code>state["self"]["allowed_directions"]</code> и <code>memory</code>.
        Первый вызов получает <code>None</code>. Память сохраняется между
        тактами как JSON до 16 КиБ.
      </p>
      <dl>
        <dt>Поле и время</dt>
        <dd>
          <code>width</code>, <code>height</code>, <code>tick</code>,{' '}
          <code>ticks_remaining</code>. Координаты <code>[x, y]</code>{' '}
          отсчитываются от левого верхнего угла с нуля.
        </dd>
        <dt>Змейки</dt>
        <dd>
          <code>self</code> и <code>opponents</code>. У каждой есть{' '}
          <code>id</code>, <code>name</code>, <code>head</code>,{' '}
          <code>body</code> от головы к хвосту, <code>direction</code>,{' '}
          <code>length</code>, <code>score</code>, <code>alive</code>,{' '}
          <code>movement</code> и <code>effects.shield_ticks</code>.
        </dd>
        <dt>Движение</dt>
        <dd>
          <code>movement</code> содержит <code>origin</code>,{' '}
          <code>target</code>, <code>progress</code>, <code>in_water</code>,{' '}
          <code>slowed</code> и <code>can_turn</code>. На середине водного шага{' '}
          <code>head</code> содержит дробную координату, а <code>progress</code>{' '}
          равен 0.5.
        </dd>
        <dt>Объекты</dt>
        <dd>
          <code>obstacles</code>, <code>water</code> и <code>poison</code>{' '}
          содержат координаты. У <code>food</code> есть <code>cell</code> и{' '}
          <code>kind</code> (<code>normal</code> или <code>gold</code>). У{' '}
          <code>powerups</code> есть <code>cell</code>, <code>kind</code>,{' '}
          <code>duration</code>, <code>blocks_poison</code> и{' '}
          <code>blocks_water_slowdown</code>.
        </dd>
      </dl>
      <p>
        Змейки ходят одновременно и не разворачиваются на 180°. При столкновении
        со стеной, телом или головой змейка погибает. Общая цель или обмен
        клетками голов убивает обеих. Хвост освобождается на полном ходе без
        роста.
      </p>
      <p>
        Шаг в воду занимает два такта. Поворот возможен только из целой клетки.
        Обычная и золотая еда дают 10 и 30 очков и добавляют сегмент. Яд
        отнимает сегмент. При длине 2 яд смертелен. Щит на 10 тактов убирает
        замедление водой и поглощает один яд.
      </p>
      <p>
        Матч выигрывает единственная выжившая змейка. По лимиту тактов
        сравниваются очки выживших, при равенстве объявляется ничья. Если
        погибли все, победителя нет.
      </p>
      <p>
        На решение отводится 100 мс. Доступны <code>collections</code>,{' '}
        <code>functools</code>, <code>heapq</code>, <code>itertools</code>,{' '}
        <code>math</code>, <code>operator</code> и <code>random</code>. При
        ошибке змейка продолжает движение в текущем направлении с прежней
        памятью.
      </p>
    </details>
  )
}
