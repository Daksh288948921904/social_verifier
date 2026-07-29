import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'

export function useClips(sessionId: string) {
  return useQuery({
    queryKey: ['clips', sessionId],
    queryFn: () => api.listClips(sessionId),
    refetchInterval: 10_000,
  })
}

export function useClipMutations(sessionId: string) {
  const queryClient = useQueryClient()
  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['clips', sessionId] })

  const rename = useMutation({
    mutationFn: ({ id, title }: { id: string; title: string }) => api.renameClip(id, { title }),
    onSuccess: invalidate,
  })

  const retrim = useMutation({
    mutationFn: ({ id, start, end }: { id: string; start: number; end: number }) =>
      api.retrimClip(id, start, end),
    onSuccess: invalidate,
  })

  const remove = useMutation({
    mutationFn: (id: string) => api.deleteClip(id),
    onSuccess: invalidate,
  })

  return { rename, retrim, remove }
}
