import { useEffect, useState, type MouseEvent } from 'react'
import { AgentAlert, AgentButton, AgentDrawer, AgentSkeleton } from '@bv-ds/ui'
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
  // 레이어 밖(어두운 배경)을 누르면 닫는다 — 모달 dialog는 배경 클릭도 자신이 받으므로 패널 영역 밖인지 좌표로 가린다
  const onBackdrop = (e: MouseEvent<HTMLDialogElement>) => {
    if (e.target !== e.currentTarget) return
    const r = e.currentTarget.getBoundingClientRect()
    if (e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom) onClose()
  }
  return (
    <AgentDrawer className="pds-drawer" onClick={onBackdrop} open={!!id} onClose={onClose} title={title}
      description={id ? `포털 ID ${id}` : undefined}
      actions={<AgentButton variant="secondary" size="sm" onClick={onClose}>닫기</AgentButton>}>
      <button type="button" className="pds-drawer-x" onClick={onClose} aria-label="닫기" title="닫기 (Esc)">✕</button>
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
