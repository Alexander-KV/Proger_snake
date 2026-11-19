import { defaultKeymap, history, historyKeymap } from '@codemirror/commands'
import { python } from '@codemirror/lang-python'
import {
  defaultHighlightStyle,
  indentOnInput,
  syntaxHighlighting,
} from '@codemirror/language'
import { EditorState } from '@codemirror/state'
import {
  EditorView,
  highlightActiveLine,
  keymap,
  lineNumbers,
} from '@codemirror/view'
import { useEffect, useRef, type RefObject } from 'react'

export const template = `def decide(state, memory):
    snake = state["self"]
    return {
        "direction": snake["direction"],
        "memory": memory,
    }
`

export function AlgorithmEditor({
  source,
  onChange,
  editorRef,
}: {
  source: string
  onChange: (value: string) => void
  editorRef: RefObject<EditorView | null>
}) {
  const host = useRef<HTMLDivElement>(null)
  const initial = useRef(source)

  useEffect(() => {
    const instance = new EditorView({
      parent: host.current!,
      state: EditorState.create({
        doc: initial.current,
        extensions: [
          python(),
          history(),
          keymap.of([...defaultKeymap, ...historyKeymap]),
          lineNumbers(),
          highlightActiveLine(),
          indentOnInput(),
          syntaxHighlighting(defaultHighlightStyle),
          EditorView.contentAttributes.of({
            'aria-label': 'Код алгоритма Python',
            spellcheck: 'false',
          }),
          EditorView.updateListener.of((change) => {
            if (change.docChanged) onChange(change.state.doc.toString())
          }),
        ],
      }),
    })
    editorRef.current = instance
    return () => {
      editorRef.current = null
      instance.destroy()
    }
  }, [editorRef, onChange])

  useEffect(() => {
    const instance = editorRef.current
    if (instance && instance.state.doc.toString() !== source) {
      instance.dispatch({
        changes: { from: 0, to: instance.state.doc.length, insert: source },
      })
    }
  }, [source, editorRef])

  return <div ref={host} className="algorithm-editor" />
}
