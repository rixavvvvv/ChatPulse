# ChatPulse Frontend Architecture

## Overview

ChatPulse frontend is built with React 18, TypeScript, and Next.js 14, providing a modern, scalable, and responsive web application for bulk messaging management. The architecture emphasizes operational usability, performance, and maintainability.

## Tech Stack

- **Framework**: Next.js 14.2 with App Router
- **UI Library**: React 18.3 with TypeScript
- **Styling**: Tailwind CSS 3.4
- **State Management**: Zustand 4.4
- **Data Fetching**: TanStack Query 5.28 (React Query)
- **Form Handling**: React Hook Form 7.48 + Zod validation
- **Tables**: TanStack React Table 8.17
- **Real-time**: Socket.IO client 4.7
- **Theming**: next-themes 0.2
- **Notifications**: react-hot-toast 2.4
- **HTTP Client**: Axios 1.6 with interceptors
- **Animations**: Framer Motion 10.16

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    Next.js Application                        │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌──────────────────────────────────────────────────────┐  │
│  │            Root Provider                              │  │
│  │  ├─ AppThemeProvider (next-themes)                   │  │
│  │  ├─ QueryProvider (TanStack Query)                   │  │
│  │  ├─ WebSocketProvider (Socket.IO)                    │  │
│  │  └─ Toaster (react-hot-toast)                        │  │
│  └──────────────────────────────────────────────────────┘  │
│                            ↓                                 │
│  ┌──────────────────────────────────────────────────────┐  │
│  │            Workspace Layout (App Routes)              │  │
│  │  ├─ Navbar (Theme, User Menu, Logout)                │  │
│  │  ├─ Sidebar (Navigation, Responsive)                 │  │
│  │  └─ Main Content Area                                │  │
│  └──────────────────────────────────────────────────────┘  │
│                            ↓                                 │
│  ┌──────────────────────────────────────────────────────┐  │
│  │        Pages (Dashboard, Contacts, etc.)              │  │
│  │  ├─ PageLayout (Headers, Breadcrumbs, Actions)       │  │
│  │  ├─ DataTable (TanStack Table Wrapper)               │  │
│  │  └─ Modals/Drawers (UI Primitives)                   │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

## Folder Structure

```
frontend/
├── app/                          # Next.js App Router
│   ├── (auth)/                   # Auth routes (login, signup)
│   ├── (workspace)/              # Protected workspace routes
│   │   ├── dashboard/
│   │   ├── inbox/
│   │   ├── campaigns/
│   │   ├── contacts/
│   │   ├── segments/
│   │   ├── workflows/
│   │   ├── analytics/
│   │   ├── automations/
│   │   ├── settings/
│   │   └── layout.tsx            # Workspace layout with nav
│   ├── layout.tsx                # Root layout with providers
│   ├── page.tsx                  # Home page
│   └── globals.css               # Global styles
│
├── components/                   # React components
│   ├── layout/                   # Layout components
│   │   ├── navbar.tsx            # Top navigation bar
│   │   ├── sidebar.tsx           # Side navigation (responsive)
│   │   ├── app-layout.tsx        # Main layout wrapper
│   │   ├── page-layout.tsx       # Page header wrapper
│   │   └── breadcrumbs.tsx       # Breadcrumb navigation
│   └── ui/                       # Reusable UI primitives
│       ├── button.tsx
│       ├── input.tsx
│       ├── card.tsx
│       ├── modal.tsx             # Modal dialogs
│       ├── drawer.tsx            # Side drawer panels
│       ├── tabs.tsx              # Tab navigation
│       ├── pagination.tsx        # Pagination controls
│       ├── checkbox.tsx          # Checkbox input
│       ├── data-table.tsx        # TanStack table wrapper
│       ├── filters.tsx           # Filtering UI
│       └── states.tsx            # Loading, error, empty states
│
├── hooks/                        # Custom React hooks
│   ├── index.ts                  # UI hooks (useDisclosure, usePagination, etc.)
│   ├── useAsync.ts               # Async operations
│   └── queries.ts                # TanStack Query hooks
│
├── services/                     # API integration layer
│   ├── api.ts                    # Axios client with interceptors
│   └── api-services.ts           # Service methods for each domain
│
├── stores/                       # Zustand state management
│   ├── auth.ts                   # Authentication state
│   └── ui.ts                     # UI state (theme, sidebar)
│
├── providers/                    # React context providers
│   ├── root-provider.tsx         # Combines all providers
│   ├── query-provider.tsx        # TanStack Query setup
│   ├── theme-provider.tsx        # next-themes setup
│   └── [index.tsx]
│
├── websocket/                    # Real-time communication
│   └── provider.tsx              # Socket.IO context provider
│
├── types/                        # TypeScript type definitions
│   └── index.ts                  # All domain types
│
├── lib/                          # Utility functions
│   ├── utils.ts                  # Format, string helpers
│   └── utils/
│       └── format.ts             # Date/time formatters
│
└── public/                       # Static assets
```

## Key Components

### 1. **Root Provider** (`providers/root-provider.tsx`)
Combines all application providers:
- `AppThemeProvider`: Dark/light mode support
- `QueryProvider`: TanStack Query configuration
- `WebSocketProvider`: Real-time connectivity
- `Toaster`: Global toast notifications

### 2. **Navbar** (`components/layout/navbar.tsx`)
- User profile menu
- Theme toggle (dark/light)
- Logout functionality
- Responsive design

### 3. **Sidebar** (`components/layout/sidebar.tsx`)
- Navigation links (9 main sections)
- Active route highlighting
- Mobile responsive with backdrop
- Auto-close on mobile navigation

### 4. **Layout Patterns**

#### App Layout
```typescript
<AppLayout>
  <Navbar />
  <Sidebar />
  <main>{children}</main>
</AppLayout>
```

#### Page Layout
```typescript
<PageLayout
  title="Campaigns"
  description="Manage messaging campaigns"
  breadcrumbs={[...]}
  actions={<Button>New</Button>}
>
  {/* Content */}
</PageLayout>
```

### 5. **State Management**

#### Auth Store (Zustand)
```typescript
const { user, workspace, isAuthenticated, setUser, logout } = useAuthStore();
```

#### UI Store (Zustand with persistence)
```typescript
const { sidebarOpen, theme, toggleSidebar, setTheme } = useUIStore();
```

## Data Flow

### API Request Flow
```
Component Hook (useContacts)
    ↓
TanStack Query Hook
    ↓
Service Method (contactsService.list)
    ↓
Axios Client with Auth Token
    ↓ Interceptors handle auth/errors
API Server (FastAPI)
```

### State Update Flow
```
User Action (click, submit)
    ↓
Event Handler / Form Submit
    ↓
Mutation Hook (useCreateContact)
    ↓
Service API Call
    ↓
Toast Notification + Query Invalidation
    ↓
Component Re-render with New Data
```

### Real-Time Flow
```
WebSocketProvider (Socket.IO)
    ↓
Connect on App Load (if authenticated)
    ↓
Listen to Events:
  - typing_start / typing_stop
  - user_online / user_offline
  - conversation_updated
  - message_received
    ↓
Update Component State / Query Cache
    ↓
Re-render UI
```

## Page Structure

Each page follows a consistent pattern:

```typescript
export default function PageName() {
  // 1. Data fetching
  const { data, isLoading } = useContacts();
  
  // 2. Local state
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const modal = useDisclosure();
  const pagination = usePagination();
  
  // 3. Mutations
  const createMutation = useCreateContact();
  
  // 4. Render
  return (
    <PageLayout
      title="Page Name"
      actions={<Button onClick={modal.onOpen}>New</Button>}
    >
      {/* Search/Filters */}
      <Card>
        <DataTable {...} />
      </Card>
      
      {/* Modal */}
      <Modal isOpen={modal.isOpen} onClose={modal.onClose}>
        {/* Form */}
      </Modal>
    </PageLayout>
  );
}
```

## UI Primitives Catalog

### Basic Components
- **Button**: default, secondary, destructive, ghost, outline
- **Input**: Text input with dark mode support
- **Card**: Container with header, title, description, content
- **Checkbox**: Native checkbox with accent colors

### Layout Components
- **Modal**: Centered dialog with backdrop
- **Drawer**: Side panel (left/right) with content
- **Pagination**: Numbered pagination controls
- **Tabs**: Tab navigation with icons

### Data Components
- **DataTable**: TanStack table wrapper with sorting/selection
- **Filters**: Multi-select filter UI with counts
- **Loading**: Spinner and loading text
- **EmptyState**: Icon + message + optional action
- **ErrorBoundary**: Catch and display errors

## Dark/Light Mode

Implemented using `next-themes`:

```typescript
const { theme, setTheme } = useTheme();
// "light" | "dark" | "system"
```

- Stored in Zustand with persistence
- Applied via `<html class="dark">` selector
- Tailwind dark mode variant: `dark:bg-gray-950`

## Responsive Design

Breakpoints (Tailwind):
- Mobile: < 640px
- Tablet: 640px - 1024px
- Desktop: > 1024px

Responsive patterns:
```typescript
// Sidebar: hidden on mobile, visible on md+
className="md:block"

// Grid: 1 col mobile, 2+ cols tablet/desktop
className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4"

// Hide/show elements
className="hidden md:flex"
```

## Performance Optimizations

1. **Code Splitting**: Next.js automatic route-based splitting
2. **Image Optimization**: Next.js Image component
3. **Query Caching**: TanStack Query with 5min stale time
4. **Memoization**: `useMemo` for expensive computations
5. **Lazy Loading**: `React.lazy` for heavy components

## Error Handling

### API Errors
```typescript
axios interceptor → toast.error → clear token on 401
```

### Component Errors
```typescript
<ErrorBoundary>
  <App />
</ErrorBoundary>
```

### Form Validation
```typescript
const form = useForm({ resolver: zodResolver(schema) });
```

## Authentication Flow

1. User logs in → receives JWT token
2. Token stored in `localStorage`
3. Axios interceptor adds token to all requests
4. 401 response → clear token, redirect to login
5. WebSocket connects with token in auth payload

## WebSocket Integration

Events handled:
- `connect`: Connection established
- `disconnect`: Connection lost
- `typing_start/stop`: Typing indicators
- `user_online/offline`: Presence updates
- `message_received`: New messages
- `conversation_updated`: Conversation changes

Usage:
```typescript
const { socket, isConnected, typingUsers } = useWebSocket();

socket?.emit('typing_start', { conversation_id: 1 });
```

## Best Practices

### Component Organization
- One component per file (unless closely related)
- Named exports for components
- Prop interfaces separate from implementation
- Use React.forwardRef for reusable UI components

### State Management
- Zustand for global state (auth, UI)
- useState for local component state
- TanStack Query for server state
- React Context for deeply nested state

### Naming Conventions
- Components: PascalCase (Button, DataTable)
- Files/folders: kebab-case (my-component.tsx)
- Hooks: camelCase starting with 'use' (useContacts)
- Constants: UPPER_SNAKE_CASE (API_URL)

### Type Safety
- No `any` types (use `unknown` if necessary)
- Export types for props and state
- Define all API response types
- Use discriminated unions for variants

## Scaling Patterns

### Adding a New Page

1. Create folder: `app/(workspace)/new-feature/`
2. Add `page.tsx` with PageLayout
3. Create hooks: `hooks/queries.ts` → `useNewFeature()`
4. Create services: `services/api-services.ts` → `newFeatureService`
5. Add navigation link in `components/layout/sidebar.tsx`

### Adding a New Entity

1. Add type in `types/index.ts`
2. Create service in `services/api-services.ts`
3. Create hooks in `hooks/queries.ts`
4. Create page with DataTable
5. Create modal/form for create/edit

## Configuration

### Environment Variables
```bash
NEXT_PUBLIC_API_URL=http://localhost:8000/api
NEXT_PUBLIC_SOCKET_URL=http://localhost:8000
```

### Theme Colors (Tailwind)
Customized in `tailwind.config.ts`:
- Primary: blue-600
- Secondary: gray-200
- Destructive: red-600
- Background dark: gray-950

## Deployment

### Development
```bash
npm install
npm run dev  # http://localhost:3000
```

### Production Build
```bash
npm run build
npm run start
```

### Docker
```dockerfile
FROM node:18-alpine
WORKDIR /app
COPY package.json ./
RUN npm install
COPY . .
RUN npm run build
EXPOSE 3000
CMD ["npm", "run", "start"]
```

## Monitoring

Key metrics to track:
- Page load time
- Time to interactive
- Core Web Vitals
- Error rate by component
- Query cache hit rate
- WebSocket connection uptime

## Future Enhancements

1. Offline support (Service Workers)
2. Advanced analytics dashboard
3. Workflow builder UI
4. Contact import wizard
5. Campaign template library
6. Real-time collaboration features
7. Export/reporting capabilities
8. Advanced filtering and search

## Summary

The ChatPulse frontend is built on proven patterns and libraries, prioritizing:
- **Simplicity**: Clear folder structure and component organization
- **Scalability**: Service layer, hooks, and provider patterns
- **Type Safety**: TypeScript throughout
- **Performance**: Query caching, code splitting, lazy loading
- **Maintainability**: Consistent patterns and naming conventions
- **User Experience**: Dark mode, responsive design, error handling

This foundation supports rapid feature development while maintaining code quality and user experience standards.
