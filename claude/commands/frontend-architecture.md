# Frontend Architecture Skill

Apply these architectural principles when building or refactoring frontend components, pages, and state management. Translates OO design patterns into React/Next.js idioms.

## When This Activates
Component creation, page layouts, state management decisions, hook design, prop API design.

## Component Design

### Single Responsibility
- One component = one reason to change. If a component handles data fetching AND rendering AND error states, split it.
- Container/presenter split when a component grows: container handles logic, presenter handles display.
- If you're passing a boolean prop that switches behavior, you probably need two components (Open/Closed).

### Composition Over Configuration
- Compound components over prop-heavy monoliths: `<Tabs><Tab /><TabPanel /></Tabs>` not `<Tabs items={[...]} renderItem={...} />`.
- Children and slots over render props where possible — simpler mental model.
- Compose small primitives into larger composites. Don't build god components.

### Props as Narrow Interfaces
- Don't pass full objects when a component only needs 2-3 fields (Interface Segregation).
- Destructure props at the function signature level — makes the contract explicit.
- Callbacks over internal state when the parent needs to know. Lift state only when coordination requires it.

## State Architecture

### Colocate by Default
- State lives in the component that uses it. Lift only when a sibling needs it.
- Server Components for data that doesn't need client interactivity.
- URL state (search params) for anything that should survive refresh or be shareable.

### Custom Hooks as Facades
- Complex logic behind a simple hook interface: `useRegeneration()` hides WebSocket, polling, state machine.
- One hook = one concern. Don't bundle unrelated state into a single hook.
- Hooks that fetch data return `{ data, isLoading, error }` — consistent contract.

## Layer Architecture
- **Primitives** (ui/): Button, Card, Input, Badge — stateless, styled, reusable everywhere.
- **Composites** (widget/): Widget, WidgetHeader, WidgetContent — combine primitives with domain logic.
- **Domain pages**: Compose widgets, handle routing, manage page-level state.
- Build from existing primitives before creating new ones. Check what exists first.

## Anti-patterns
- Don't build new primitives without checking ui/ first.
- Don't use `useEffect` for derived state — compute it during render.
- Don't prop-drill through more than 2 levels — use context or composition.
- Don't put API calls in components — use hooks or server actions.

## Deep Reference
Search OV `resources/agents/frontend-architecture-reference` for OO patterns and SOLID applied to frontend.
