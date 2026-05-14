# ChatPulse Frontend

Professional bulk messaging platform frontend built with React, TypeScript, and Tailwind CSS.

## Features

✅ **Scalable Architecture**
- Service layer for API integration
- Zustand for state management
- TanStack Query for data fetching
- Type-safe with TypeScript

✅ **Modern UI/UX**
- Dark/light mode support
- Fully responsive design
- Accessible components
- Smooth animations with Framer Motion

✅ **Real-Time Communication**
- Socket.IO integration for live updates
- Typing indicators
- Presence tracking
- Real-time notifications

✅ **Data Management**
- TanStack Table for complex tables
- Pagination and filtering
- Form validation with Zod
- Error boundaries and loading states

✅ **Developer Experience**
- Clear folder structure
- Reusable components and hooks
- Comprehensive documentation
- TypeScript for type safety

## Quick Start

### Prerequisites
- Node.js 18+
- npm or yarn
- Backend API running (http://localhost:8000)

### Installation

```bash
# Install dependencies
npm install

# Set up environment
cp .env.example .env.local

# Add configuration
echo "NEXT_PUBLIC_API_URL=http://localhost:8000/api" >> .env.local
```

### Development

```bash
npm run dev
# Open http://localhost:3000
```

### Production Build

```bash
npm run build
npm run start
```

## Architecture

See [ARCHITECTURE.md](./ARCHITECTURE.md) for detailed architecture documentation.

### Key Components

- **Providers**: Query, Theme, WebSocket providers
- **Layout**: Navbar, Sidebar, AppLayout, PageLayout
- **UI Primitives**: Button, Input, Card, Modal, Drawer, Table
- **Pages**: Dashboard, Contacts, Campaigns, Workflows, Analytics, Settings
- **Hooks**: Data fetching (useContacts), UI (useDisclosure), utilities
- **Services**: API client and service methods
- **State**: Zustand stores for auth and UI

### Folder Structure

```
frontend/
├── app/                    # Next.js app routes
├── components/             # Reusable components
├── hooks/                  # Custom hooks
├── services/               # API integration
├── stores/                 # Zustand state
├── providers/              # Context providers
├── websocket/              # Real-time communication
├── types/                  # TypeScript definitions
├── lib/                    # Utilities
└── ARCHITECTURE.md         # Detailed docs
```

## Stack

| Layer | Technology |
|-------|------------|
| Framework | Next.js 14 |
| UI Framework | React 18 + TypeScript |
| Styling | Tailwind CSS 3 |
| State | Zustand 4 |
| Data Fetching | TanStack Query 5 |
| Forms | React Hook Form + Zod |
| Tables | TanStack Table 8 |
| Real-time | Socket.IO 4 |
| Theme | next-themes 0.2 |
| Notifications | react-hot-toast 2 |
| HTTP | Axios 1.6 |
| Animations | Framer Motion 10 |

## Pages

### Dashboard
Overview of key metrics, recent campaigns, quick actions

### Inbox
Conversation management, message history, contact details

### Campaigns
Campaign creation, scheduling, analytics, delivery tracking

### Contacts
Contact management, import, tagging, segmentation

### Segments
Create and manage contact segments for targeting

### Workflows
Workflow builder, automation triggers, action sequences

### Analytics
Performance metrics, engagement tracking, reporting

### Automations
Trigger-based automation rules and actions

### Settings
Workspace configuration, team management, integrations

## Configuration

### Environment Variables

```bash
# Required
NEXT_PUBLIC_API_URL=http://localhost:8000/api

# Optional
NEXT_PUBLIC_SOCKET_URL=http://localhost:8000
```

### Tailwind Configuration

See `tailwind.config.ts` for theme customization:
- Colors, typography, spacing, breakpoints
- Dark mode support
- Custom utilities

## Development

### Project Structure

- `app/` - Next.js routes and layouts
- `components/` - React components
- `hooks/` - Custom React hooks
- `services/` - API integration layer
- `stores/` - Zustand state stores
- `types/` - TypeScript type definitions
- `lib/` - Utility functions
- `public/` - Static assets

### Adding a New Page

1. Create directory: `app/(workspace)/feature-name/`
2. Add `page.tsx` with PageLayout component
3. Create hooks in `hooks/queries.ts`
4. Create services in `services/api-services.ts`
5. Add navigation link in `components/layout/sidebar.tsx`

### Adding a Component

1. Create in `components/ui/` or `components/layout/`
2. Export from component file
3. Add TypeScript interfaces for props
4. Use Tailwind for styling
5. Support dark mode with `dark:` variants

### Code Style

- **Components**: Functional with hooks
- **State**: Zustand for global, useState for local
- **Styling**: Tailwind CSS only
- **Types**: TypeScript interfaces over types
- **Naming**: camelCase for functions/hooks, PascalCase for components

## Performance Tips

1. **Query Caching**: TanStack Query caches data for 5 minutes
2. **Code Splitting**: Automatic per-route via Next.js
3. **Image Optimization**: Use Next.js Image component
4. **Memoization**: React.memo for heavy components
5. **Lazy Loading**: React.lazy for modal content

## Testing

### Unit Tests
```bash
npm test
```

### Integration Tests
```bash
npm run test:integration
```

### E2E Tests
```bash
npm run test:e2e
```

## Deployment

### Vercel (Recommended)
```bash
# Push to GitHub
git push origin main

# Deploy via Vercel dashboard
# Set NEXT_PUBLIC_API_URL in environment
```

### Docker
```bash
docker build -t chatpulse-frontend .
docker run -p 3000:3000 -e NEXT_PUBLIC_API_URL=... chatpulse-frontend
```

### Manual
```bash
npm run build
npm run start
```

## Troubleshooting

### Port Already in Use
```bash
lsof -i :3000
kill -9 <PID>
```

### Module Not Found
```bash
rm -rf node_modules .next
npm install
npm run dev
```

### API Connection Issues
1. Check `NEXT_PUBLIC_API_URL` in `.env.local`
2. Ensure backend is running
3. Check CORS settings in backend
4. Check browser console for errors

## Contributing

1. Create feature branch: `git checkout -b feature/name`
2. Follow code style conventions
3. Add TypeScript types
4. Test changes locally
5. Create pull request

## Documentation

- [Architecture Guide](./ARCHITECTURE.md) - Detailed system design
- [Component Catalog](./COMPONENTS.md) - Available components
- [API Services](./services/api-services.ts) - API integration methods
- [Type Definitions](./types/index.ts) - Data types and interfaces

## License

Proprietary - ChatPulse

## Support

For issues or questions:
1. Check [ARCHITECTURE.md](./ARCHITECTURE.md)
2. Review component source code
3. Check browser console for errors
4. Contact development team

---

Built with ❤️ using React, TypeScript, and Tailwind CSS
