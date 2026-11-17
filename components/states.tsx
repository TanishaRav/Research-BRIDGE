"use client";

import { Component, type ReactNode } from "react";
import { ApiError } from "@/lib/api";
import { Button, StatusCallout } from "./ui";

export function LoadError({
  error,
  onRetry,
}: {
  error: ApiError;
  onRetry?: () => void;
}) {
  const offline = error.status === 0;
  const forbidden = error.status === 403 || error.status === 401;
  const tone = offline ? "warning" : forbidden ? "info" : "error";
  const title = offline
    ? "Cannot reach the API"
    : forbidden
      ? "This demo persona cannot view that data"
      : "Something went wrong";
  return (
    <StatusCallout tone={tone} title={title}>
      <p>{error.message}</p>
      {onRetry && !forbidden ? (
        <div className="mt-3">
          <Button variant="secondary" onClick={onRetry}>
            Try again
          </Button>
        </div>
      ) : null}
    </StatusCallout>
  );
}

interface BoundaryState {
  error: Error | null;
}

export class ErrorBoundary extends Component<{ children: ReactNode }, BoundaryState> {
  state: BoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): BoundaryState {
    return { error };
  }

  render() {
    if (this.state.error) {
      return (
        <div className="p-6">
          <StatusCallout tone="error" title="The view failed to render">
            <p>{this.state.error.message}</p>
            <div className="mt-3">
              <Button variant="secondary" onClick={() => this.setState({ error: null })}>
                Dismiss
              </Button>
            </div>
          </StatusCallout>
        </div>
      );
    }
    return this.props.children;
  }
}
