import { useEffect, useState } from 'react'
import { AgentAlert, AgentDrawer, AgentSkeleton } from '@bv-ds/ui'
import { api, type DatasetOut } from './api'
import { Markdown, type OpenDataset } from './md'

// 데이터 설명서(dossier) — 지식 체계에 없는 ID는 포털 목록 링크만 안내한다.
export function DatasetDrawer({ id, onClose, open }: { id: string | null; onClose: () => void; open: OpenDataset }) {
  const [data, setData] = useState<DatasetOut | null>(null)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => {
    if (!id) return
    setData(null)
    setErr(null)
    api.dataset(id).then(setData).catch((e: Error) => setErr(e.message))
  }, [id])

  const title = data?.dataset.title ?? id ?? ''
  return (
    <AgentDrawer open={!!id} onClose={onClose} title={title} description={id ? `포털 ID ${id}` : undefined}>
      {err ? (
        <AgentAlert tone="info" title="지식 체계에 없는 데이터">
          포털 목록에만 있는 데이터입니다.{' '}
          <a href={`https://www.data.go.kr/data/${id}/openapi.do`} target="_blank" rel="noreferrer">포털에서 보기</a>
        </AgentAlert>
      ) : !data ? (
        <AgentSkeleton />
      ) : data.dossier_md ? (
        <Markdown text={data.dossier_md} open={open} />
      ) : (
        <pre className="pds-pre">{JSON.stringify(data.dataset, null, 1)}</pre>
      )}
    </AgentDrawer>
  )
}
