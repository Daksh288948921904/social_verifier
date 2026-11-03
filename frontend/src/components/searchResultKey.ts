// Shared between SearchResultCard and SearchPage's "Smart-pick all", which
// both write the latest row for a result into this query.
export const searchResultKey = (id: string) => ['search-result', id]
