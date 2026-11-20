# Snake Arena

**Snake Arena** — учебное веб-приложение для соревнования алгоритмов, управляющих змейками.

Команда разрабатывает
стратегию: получает наблюдение об игровом поле и возвращает направление движения.

Несколько независимых алгоритмов
соревнуются по общим правилам, а зрители наблюдают за матчем и результатами.

## Идея и сценарий

Ценность проекта — **соревнование стратегий**, а не ручное управление змейками.

1. Организатор собирает участников в лобби и запускает подготовку, задав время в минутах.
2. Команды пишут и проверяют Python-алгоритмы. Пока таймер идёт, они могут запускать тренировку на отдельном
   настраиваемом поле против стандартных ботов.
3. Каждая отправка сохраняет исходник отдельной версией с именем «Версия #N» и временем отправки до минуты. Участник
   может переименовать версию и отдельной кнопкой выбрать её для игры.
4. По серверному дедлайну выбранные версии фиксируются и матч начинается автоматически. Без явного выбора используется
   последняя отправка. Команда без отправок пропускает раунд. Тренировка не влияет на таймер или выбор команды.
5. Алгоритмы получают состояние одного такта и возвращают решение. Движок применяет решения одновременно. Участники
   следят за полем, очками и итоговой таблицей.

Реализация описана в [текущем состоянии](docs/current-state.md), а детали правил —
в [спецификации подготовки алгоритмов и онлайн-матчей](docs/superpowers/specs/2026-11-19-algorithm-matches-design.md).

## Стек

| Часть          | Текущие технологии                                 |
|----------------|----------------------------------------------------|
| Frontend       | React, TypeScript, Vite, Tailwind CSS, CodeMirror  |
| Backend        | Python 3.11+, FastAPI, SQLModel                    |
| Исполнитель    | Один контейнер Docker, CPython 3.13, Linux seccomp |
| Хранение       | SQLite, локальный файл в `data/`                   |
| Форматирование | Prettier (frontend), Ruff (backend)                |
| Проверки       | ESLint, TypeScript/Vite build, pytest              |

Список матчей, лобби, команды организатора и трансляция раунда используют одно соединение WebSocket.

## Локальный запуск

Понадобятся Git, Node.js 24 с npm, Python 3.11+, uv и запущенный Docker.

1. Клонируйте репозиторий и перейдите в его каталог.

   ```bash
   git clone https://github.com/Alexander-KV/Proger_snake.git
   cd Proger_snake
   ```

2. Скопируйте шаблон в `.env.local`.

   ```bash
   cp -n .env.local.example .env.local
   ```

3. Сгенерируйте токен и вставьте выведенную строку после `SNAKE_RUNNER_TOKEN=` в файле `.env.local`.

   ```bash
   python3 -c 'import secrets; print(secrets.token_urlsafe(32))'
   ```

   > Не добавляйте `.env.local` в Git.

4. Соберите образ и запустите контейнер `snake-arena-runner` для изолированного выполнения Python-алгоритмов участников.

   ```bash
   docker build -t snake-arena-runner backend/training &&
   docker run --rm -d --name snake-arena-runner --read-only --init \
     --cap-drop ALL --security-opt no-new-privileges --memory 512m --pids-limit 32 \
     --cpus 4 -p 127.0.0.1:8765:8765 --env-file .env.local snake-arena-runner
   ```

5. Запустите backend в первом терминале из корня репозитория.

   ```bash
   uv sync --project backend --locked
   uv run --project backend --locked uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000 --no-proxy-headers
   ```

6. Запустите frontend во втором терминале из корня репозитория.

   ```bash
   npm ci
   npm run dev
   ```

7. Откройте адрес, который покажет Vite (обычно `http://localhost:5173`).

### Необязательно

- **Матч по локальной сети.** Вместо `npm run dev` выполните команду ниже, подставив IPv4-адрес своего компьютера вместо
  `192.168.1.10`. На устройствах в той же сети откройте `http://192.168.1.10:5173` с тем же IP-адресом.

  ```bash
  npm run dev -- --host 192.168.1.10 --strictPort
  ```

  > Оставьте backend на `127.0.0.1:8000`. Не публикуйте dev-сервер в интернете.

- **Остановка контейнера.** Выполните `docker stop snake-arena-runner`.

## Проверки

```bash
npm run lint
npm run build
npm run format:check
uv run --project backend --locked python -m pytest backend/tests
uv run --project backend --locked ruff format --check backend
```

С запущенным контейнером и заданным `SNAKE_RUNNER_TOKEN` pytest также проверяет реальное исполнение, изоляцию, память и
таймауты. Приёмка в браузере покрывает подготовку, тренировку, выбор версий, онлайн-матч и результат.

## Документация

- [GitHub Issues](https://github.com/Alexander-KV/Proger_snake/issues)
- [docs/current-state.md](docs/current-state.md) — состояние реализации, статус требований
- [docs/architecture.md](docs/architecture.md) — структура проекта
- [docs/design.md](docs/design.md) — правила оформления и анимаций, дизайн-система проекта
- [docs/development.md](docs/development.md) — правила написания кода, требования к разработке