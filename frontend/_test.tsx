  return value.match(/BV[0-9A-Za-z]+/)?.[0] || ''
}

const VIDEO_URL_PATTERN =
  /(?:https?:\/\/|www\.|b23\.tv\/|(?:[\w-]+\.)?bilibili\.com\/)[^\s<>"'`|\\\u3000-\u303f\uff00-\uff65]+/gi
const BILIBILI_ID_PATTERN = /\b(?:BV[0-9A-Za-z]{10}|av\d+)\b/gi

function normalizeVideoUrlCandidate(candidate: string): string | null {
  const trimmed = candidate
    .trim()
    .replace(/^[<>"'`([{]+/, '')

                      {!template.isBuiltIn && (
                        <button
                          type="button"
                          onClick={() => handleDeletePromptTemplate(template)}
                          className="text-neutral-500 transition-colors hover:text-red-300"
                          aria-label={`删除模板 ${template.name}`}
                        >
                          <X size={12} />
                        </button>
                      )}
                    </div>
                  ))}
                </div>

                <div className="rounded-xl border border-neutral-800 bg-[#121212] px-3 py-2 text-xs text-neutral-500">
                  {activePromptTemplateId
                    ? `当前模板：${
                      allPromptTemplates.find(template => template.id === activePromptTemplateId)?.name ||
                      '未命名模板'
                    }，当前编辑会自动保存到本地草稿`
                    : '当前内容会自动保存到本地草稿，可直接编辑后保存为模板'}
                </div>

                {hasPromptContent && (
                  <div className="mt-2 flex items-center justify-end">
                    <button
                      type="button"
                      onClick={() => {
                        setPrompt('')
                        setPromptName('')
                        setActivePromptTemplateId(null)
                        clearPromptDraft()
                      }}
                      className="rounded-lg border border-neutral-800 px-4 py-1.5 text-sm font-medium text-neutral-400 transition-colors hover:border-neutral-600 hover:text-neutral-200"
                    >
                      清除
                    </button>
                  </div>
                )}
              </div>
              {promptSectionOpen &&
              <div className="mt-4">
                <div className="mb-3 flex items-center justify-between">
                  <div className="flex cursor-pointer items-center gap-2" onClick={() => setFormatSectionOpen(!formatSectionOpen)}>
                    {formatSectionOpen ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                    <h3 className="text-sm font-bold text-neutral-300">文档格式</h3>
                  </div>
                  <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => {
                      fetch('/api/v1/system/note-format', {
                        method: 'PUT',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({format: noteFormat})
                      }).then(r => r.json()).then(d => { if (d.saved) setNoteFormatSaved(true); toast.success('文档格式已保存') }).catch(() => toast.error('保存失败'))
                    }}
                    className="shrink-0 text-xs text-primary transition-colors hover:text-primary/80"
                  >
                    {noteFormatSaved ? '保存格式' : '· 未保存'}
                  </button>
                </div>
                <textarea
                  value={noteFormat}
                  onChange={e => { setNoteFormat(e.target.value); setNoteFormatSaved(false) }}
                  placeholder="在此编辑笔记输出格式模板..."
                  className="min-h-[120px] w-full resize-none rounded-xl border border-neutral-800 bg-[#141414] p-3 text-xs text-neutral-300 transition-colors placeholder:text-neutral-600 focus:border-neutral-600 focus:outline-none"
                />
              </div>}
          </div>
        </div>
        </div>
      </div>
    </div>
  )
}
