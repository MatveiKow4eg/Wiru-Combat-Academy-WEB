/**
 * Schedule Multiselect Module
 * Handles selection mode, multi-selection, and bulk deletion
 */

(function() {
  'use strict';

  // Module state
  let selectionMode = false;
  let selectedIds = new Set();
  let lastSelectedIndex = -1;

  // External dependencies (must be available globally)
  let scheduleData = [];
  let activeDay = 0;
  let api = null;
  let showToast = null;
  let loadSchedule = null;
  let closeModal = null;

  /**
   * Initialize the module with required dependencies
   */
  function init(deps) {
    if (!deps) {
      console.error('Schedule multiselect: dependencies not provided');
      return;
    }

    api = deps.api;
    showToast = deps.showToast;
    loadSchedule = deps.loadSchedule;
    closeModal = deps.closeModal;

    // Expose functions globally for onclick handlers
    window.toggleSelectionMode = toggleSelectionMode;
    window.toggleSelectAll = toggleSelectAll;
    window.deleteSelected = deleteSelected;
    window.toggleSelection = toggleSelection;

    setupKeyboardShortcuts();
  }

  /**
   * Update module state from external sources
   */
  function updateState(data, day) {
    scheduleData = data || [];
    activeDay = day;
  }

  /**
   * Enter selection mode
   */
  function enterSelectionMode() {
    selectionMode = true;
    selectedIds.clear();
    lastSelectedIndex = -1;

    const toolbar = document.getElementById('selection-toolbar');
    const selectBtn = document.getElementById('select-mode-btn');

    if (toolbar) toolbar.classList.add('active');
    if (selectBtn) {
      selectBtn.classList.add('active');
      selectBtn.setAttribute('aria-pressed', 'true');
    }

    updateSelectionUI();
  }

  /**
   * Exit selection mode
   */
  function exitSelectionMode() {
    selectionMode = false;
    selectedIds.clear();
    lastSelectedIndex = -1;

    const toolbar = document.getElementById('selection-toolbar');
    const selectBtn = document.getElementById('select-mode-btn');

    if (toolbar) toolbar.classList.remove('active');
    if (selectBtn) {
      selectBtn.classList.remove('active');
      selectBtn.setAttribute('aria-pressed', 'false');
    }

    updateSelectionUI();
  }

  /**
   * Toggle selection mode on/off
   */
  function toggleSelectionMode() {
    if (selectionMode) {
      exitSelectionMode();
    } else {
      enterSelectionMode();
    }
  }

  /**
   * Update UI to reflect current selection state
   */
  function updateSelectionUI() {
    const cards = document.querySelectorAll('.schedule-card');
    const deleteBtn = document.getElementById('delete-selected-btn');
    const selectAllBtn = document.getElementById('select-all-btn');
    const count = selectedIds.size;

    cards.forEach(card => {
      const checkbox = card.querySelector('.card-checkbox');
      const id = parseInt(card.dataset.id);

      if (selectionMode) {
        card.classList.add('selectable');
        if (checkbox) checkbox.checked = selectedIds.has(id);
        if (selectedIds.has(id)) {
          card.classList.add('selected');
          card.setAttribute('aria-selected', 'true');
        } else {
          card.classList.remove('selected');
          card.setAttribute('aria-selected', 'false');
        }
      } else {
        card.classList.remove('selectable', 'selected');
        card.removeAttribute('aria-selected');
        if (checkbox) checkbox.checked = false;
      }
    });

    // Update delete button
    if (deleteBtn) {
      const deleteText = deleteBtn.dataset.textTemplate || 'Удалить';
      deleteBtn.textContent = `${deleteText} (${count})`;
      deleteBtn.disabled = count === 0;
    }

    // Update select all button
    if (selectAllBtn) {
      const dayItems = scheduleData.filter(item => item.day_of_week === activeDay);
      const allSelected = dayItems.length > 0 && selectedIds.size === dayItems.length;
      const selectAllText = selectAllBtn.dataset.selectAllText || 'Выбрать все';
      const deselectAllText = selectAllBtn.dataset.deselectAllText || 'Снять всё';
      selectAllBtn.textContent = allSelected ? deselectAllText : selectAllText;
    }
  }

  /**
   * Toggle selection for a specific item
   */
  function toggleSelection(id, event) {
    if (!selectionMode) return;

    const dayItems = scheduleData.filter(item => item.day_of_week === activeDay);
    const currentIndex = dayItems.findIndex(item => item.id === id);

    if (event && event.shiftKey && lastSelectedIndex !== -1) {
      // Shift+click: select range
      selectRange(lastSelectedIndex, currentIndex, dayItems);
    } else if (event && (event.ctrlKey || event.metaKey)) {
      // Ctrl/Cmd+click: toggle single
      if (selectedIds.has(id)) {
        selectedIds.delete(id);
      } else {
        selectedIds.add(id);
      }
    } else {
      // Regular click: toggle single
      if (selectedIds.has(id)) {
        selectedIds.delete(id);
      } else {
        selectedIds.add(id);
      }
    }

    lastSelectedIndex = currentIndex;
    updateSelectionUI();
  }

  /**
   * Select a range of items
   */
  function selectRange(fromIndex, toIndex, items) {
    const start = Math.min(fromIndex, toIndex);
    const end = Math.max(fromIndex, toIndex);
    for (let i = start; i <= end; i++) {
      if (items[i]) {
        selectedIds.add(items[i].id);
      }
    }
  }

  /**
   * Select all items in current day
   */
  function selectAll() {
    const dayItems = scheduleData.filter(item => item.day_of_week === activeDay);
    dayItems.forEach(item => selectedIds.add(item.id));
    lastSelectedIndex = -1;
    updateSelectionUI();
  }

  /**
   * Clear all selections
   */
  function clearAll() {
    selectedIds.clear();
    lastSelectedIndex = -1;
    updateSelectionUI();
  }

  /**
   * Toggle select all / deselect all
   */
  function toggleSelectAll() {
    const dayItems = scheduleData.filter(item => item.day_of_week === activeDay);
    const allSelected = dayItems.length > 0 && selectedIds.size === dayItems.length;

    if (allSelected) {
      clearAll();
    } else {
      selectAll();
    }
  }

  /**
   * Delete all selected items
   */
  async function deleteSelected() {
    if (selectedIds.size === 0) return;

    const items = Array.from(selectedIds)
      .map(id => scheduleData.find(item => item.id === id))
      .filter(Boolean);

    if (items.length === 0) return;

    // Prepare modal content
    const count = items.length;
    const deleteBtn = document.getElementById('delete-selected-btn');
    const deleteText = deleteBtn ? deleteBtn.dataset.textTemplate || 'Удалить' : 'Удалить';
    const title = `${deleteText} ${count} занятий?`;

    let bodyHTML = '<div style="margin-bottom: 12px;">Будут удалены следующие занятия:</div>';
    bodyHTML += '<ul style="margin: 0; padding-left: 20px; max-height: 200px; overflow-y: auto;">';

    const displayItems = items.slice(0, 5);
    displayItems.forEach(item => {
      const activityDisplay = getActivityDisplay(item);
      bodyHTML += `<li><strong>${item.time}</strong> — ${activityDisplay}</li>`;
    });

    if (items.length > 5) {
      bodyHTML += `<li style="color: var(--text-secondary);">и ещё ${items.length - 5}...</li>`;
    }

    bodyHTML += '</ul>';

    showModalHTML(title, bodyHTML, async () => {
      try {
        // Delete all selected items
        const deletePromises = Array.from(selectedIds).map(id =>
          api(`/admin/schedule/item/${id}`, { method: 'DELETE' })
        );

        await Promise.all(deletePromises);

        // Clear selection and reload
        selectedIds.clear();
        lastSelectedIndex = -1;
        await loadSchedule();
        updateSelectionUI();

        showToast(`Удалено: ${count}`);
      } catch (error) {
        showToast(error.message, 'error');
      }
    });
  }

  /**
   * Get display text for activity
   */
  function getActivityDisplay(item) {
    if (item.discipline === 'other') {
      return item.activity || 'Другое';
    }

    const labels = {
      boxing: 'Бокс',
      wrestling: 'Борьба',
      mma: 'ММА'
    };

    let display = labels[item.discipline] || item.activity;
    if (item.age) {
      const cleanedAge = item.age.replace(/[aлy][.,o]*/gi, '').trim();
      display += ` ${cleanedAge}`;
    }

    return display;
  }

  /**
   * Show modal with HTML content
   */
  function showModalHTML(title, bodyHTML, onConfirm) {
    const modalTitle = document.getElementById('modal-title');
    const modalBody = document.getElementById('modal-body');
    const confirmBtn = document.getElementById('modal-confirm');
    const modal = document.getElementById('confirm-modal');

    if (modalTitle) modalTitle.textContent = title;
    if (modalBody) modalBody.innerHTML = bodyHTML;

    if (confirmBtn) {
      confirmBtn.className = 'btn btn-danger';
      confirmBtn.textContent = 'Удалить';
      confirmBtn.onclick = () => {
        if (closeModal) closeModal();
        onConfirm();
      };
    }

    if (modal) modal.classList.add('active');
  }

  /**
   * Setup keyboard shortcuts
   */
  function setupKeyboardShortcuts() {
    document.addEventListener('keydown', (e) => {
      if (!selectionMode) return;

      // Escape: exit selection mode
      if (e.key === 'Escape') {
        e.preventDefault();
        exitSelectionMode();
        return;
      }

      // Ctrl+A: select/deselect all
      if ((e.ctrlKey || e.metaKey) && e.key === 'a' && document.activeElement.tagName !== 'INPUT') {
        e.preventDefault();
        toggleSelectAll();
        return;
      }

      // Delete: open delete modal
      if (e.key === 'Delete' && selectedIds.size > 0) {
        e.preventDefault();
        deleteSelected();
        return;
      }
    });
  }

  /**
   * Reset selection when day changes
   */
  function onDayChange() {
    if (selectionMode) {
      selectedIds.clear();
      lastSelectedIndex = -1;
      updateSelectionUI();
    }
  }

  /**
   * Check if selection mode is active
   */
  function isSelectionMode() {
    return selectionMode;
  }

  /**
   * Get current selection count
   */
  function getSelectionCount() {
    return selectedIds.size;
  }

  // Export public API
  window.ScheduleMultiselect = {
    init: init,
    updateState: updateState,
    enterSelectionMode: enterSelectionMode,
    exitSelectionMode: exitSelectionMode,
    toggleSelectionMode: toggleSelectionMode,
    updateSelectionUI: updateSelectionUI,
    onDayChange: onDayChange,
    isSelectionMode: isSelectionMode,
    getSelectionCount: getSelectionCount
  };

})();
