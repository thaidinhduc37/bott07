import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { App } from './App';
import './styles/globals.css';
import './styles/training.css';
import './styles/schedule-edit.css';
import './styles/rooms.css';
import './styles/admin-create.css';
import './styles/grades.css';
import './styles/grade-entry.css';
import './styles/schedule-term.css';
import './styles/support.css';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </StrictMode>,
);
