import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { App } from './App';
import './styles/base.css';
import './styles/layout.css';
import './styles/shell.css';
import './styles/chat.css';
import './styles/dashboard.css';
import './styles/study.css';
import './styles/staff-admin.css';
import './styles/polish.css';
import './styles/training.css';
import './styles/schedule-edit.css';
import './styles/rooms.css';
import './styles/admin-create.css';
import './styles/grades.css';
import './styles/grade-entry.css';
import './styles/schedule-term.css';
import './styles/support.css';
import './styles/feedback.css';
import './styles/home.css';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </StrictMode>,
);
