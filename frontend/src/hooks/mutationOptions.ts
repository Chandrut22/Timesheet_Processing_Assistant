/** What a screen adds to a feature's mutation hook. The hook owns the API call and the
 * cache updates; the screen only adds UI effects (a toast, closing a dialog, resetting a
 * form, navigating). They run from the hook's own onSuccess, so they still run when
 * the component that started the mutation has re-mounted after the save. */
export type MutationCallbacks<TData, TVariables> = {
  onSuccess?: (data: TData, variables: TVariables) => void;
  /** E.g. put the server's field errors on the form. */
  onError?: (error: Error, variables: TVariables) => void;
};
