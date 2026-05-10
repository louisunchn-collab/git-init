(function () {
    'use strict';

    const STORAGE_KEY = 'todo-app:list';

    const form = document.getElementById('todoForm');
    const input = document.getElementById('todoInput');
    const list = document.getElementById('todoList');
    const emptyState = document.getElementById('emptyState');
    const filtersEl = document.getElementById('filters');
    const remainingText = document.getElementById('remainingText');
    const clearCompletedBtn = document.getElementById('clearCompleted');
    const dateText = document.getElementById('dateText');
    const countAll = document.getElementById('countAll');
    const countActive = document.getElementById('countActive');
    const countCompleted = document.getElementById('countCompleted');

    let todos = loadTodos();
    let currentFilter = 'all';

    init();

    function init() {
        renderDate();
        render();

        form.addEventListener('submit', handleAdd);

        filtersEl.addEventListener('click', (e) => {
            const btn = e.target.closest('.filter-btn');
            if (!btn) return;
            currentFilter = btn.dataset.filter;
            document
                .querySelectorAll('.filter-btn')
                .forEach((b) => b.classList.toggle('active', b === btn));
            render();
        });

        list.addEventListener('click', handleListClick);
        list.addEventListener('dblclick', handleListDoubleClick);

        clearCompletedBtn.addEventListener('click', () => {
            todos = todos.filter((t) => !t.completed);
            saveAndRender();
        });
    }

    function renderDate() {
        const now = new Date();
        const opts = {
            year: 'numeric',
            month: 'long',
            day: 'numeric',
            weekday: 'long',
        };
        dateText.textContent = now.toLocaleDateString('zh-CN', opts);
    }

    function handleAdd(e) {
        e.preventDefault();
        const text = input.value.trim();
        if (!text) return;
        todos.unshift({
            id: Date.now().toString(36) + Math.random().toString(36).slice(2, 6),
            text,
            completed: false,
            createdAt: Date.now(),
        });
        input.value = '';
        saveAndRender();
    }

    function handleListClick(e) {
        const item = e.target.closest('.todo-item');
        if (!item) return;
        const id = item.dataset.id;

        if (e.target.closest('.checkbox')) {
            toggleTodo(id);
        } else if (e.target.closest('.delete-btn')) {
            deleteTodo(id);
        }
    }

    function handleListDoubleClick(e) {
        const textEl = e.target.closest('.todo-text');
        if (!textEl) return;
        const item = textEl.closest('.todo-item');
        const id = item.dataset.id;
        startEdit(textEl, id);
    }

    function startEdit(textEl, id) {
        textEl.setAttribute('contenteditable', 'true');
        textEl.focus();

        const range = document.createRange();
        range.selectNodeContents(textEl);
        const sel = window.getSelection();
        sel.removeAllRanges();
        sel.addRange(range);

        const finish = (commit) => {
            textEl.removeAttribute('contenteditable');
            textEl.removeEventListener('blur', onBlur);
            textEl.removeEventListener('keydown', onKey);
            if (commit) {
                const newText = textEl.textContent.trim();
                const todo = todos.find((t) => t.id === id);
                if (todo) {
                    if (newText) {
                        todo.text = newText;
                    } else {
                        deleteTodo(id);
                        return;
                    }
                }
            }
            saveAndRender();
        };

        const onBlur = () => finish(true);
        const onKey = (ev) => {
            if (ev.key === 'Enter') {
                ev.preventDefault();
                finish(true);
            } else if (ev.key === 'Escape') {
                ev.preventDefault();
                finish(false);
            }
        };

        textEl.addEventListener('blur', onBlur);
        textEl.addEventListener('keydown', onKey);
    }

    function toggleTodo(id) {
        const todo = todos.find((t) => t.id === id);
        if (todo) {
            todo.completed = !todo.completed;
            saveAndRender();
        }
    }

    function deleteTodo(id) {
        todos = todos.filter((t) => t.id !== id);
        saveAndRender();
    }

    function getFiltered() {
        switch (currentFilter) {
            case 'active':
                return todos.filter((t) => !t.completed);
            case 'completed':
                return todos.filter((t) => t.completed);
            default:
                return todos;
        }
    }

    function render() {
        const items = getFiltered();
        list.innerHTML = '';

        items.forEach((todo) => {
            const li = document.createElement('li');
            li.className = 'todo-item' + (todo.completed ? ' completed' : '');
            li.dataset.id = todo.id;
            li.innerHTML = `
                <span class="checkbox ${todo.completed ? 'checked' : ''}" role="checkbox" aria-checked="${todo.completed}"></span>
                <span class="todo-text" title="双击编辑"></span>
                <button class="delete-btn" aria-label="删除">×</button>
            `;
            li.querySelector('.todo-text').textContent = todo.text;
            list.appendChild(li);
        });

        const total = todos.length;
        const completed = todos.filter((t) => t.completed).length;
        const active = total - completed;

        countAll.textContent = total;
        countActive.textContent = active;
        countCompleted.textContent = completed;
        remainingText.textContent = `剩余 ${active} 项`;

        emptyState.style.display = items.length === 0 ? 'block' : 'none';
        list.style.display = items.length === 0 ? 'none' : 'block';
        clearCompletedBtn.style.visibility = completed > 0 ? 'visible' : 'hidden';
    }

    function saveAndRender() {
        saveTodos();
        render();
    }

    function loadTodos() {
        try {
            const raw = localStorage.getItem(STORAGE_KEY);
            if (!raw) return [];
            const data = JSON.parse(raw);
            return Array.isArray(data) ? data : [];
        } catch (err) {
            console.warn('读取本地存储失败：', err);
            return [];
        }
    }

    function saveTodos() {
        try {
            localStorage.setItem(STORAGE_KEY, JSON.stringify(todos));
        } catch (err) {
            console.warn('保存本地存储失败：', err);
        }
    }
})();
