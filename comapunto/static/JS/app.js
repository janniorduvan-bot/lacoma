document.addEventListener('DOMContentLoaded', function () {
  document.querySelectorAll('.auto-dismiss-alert').forEach((alertEl) => {
    const timeoutMs = Number(alertEl.dataset.timeout || 4000);
    const closeAlert = () => {
      if (!alertEl || !alertEl.parentNode) return;
      if (window.bootstrap && bootstrap.Alert) {
        const instance = bootstrap.Alert.getOrCreateInstance(alertEl);
        instance.close();
      } else {
        alertEl.classList.remove('show');
        alertEl.classList.add('d-none');
      }
    };

    const existingTimer = alertEl.dataset.dismissTimer;
    if (existingTimer) {
      clearTimeout(Number(existingTimer));
    }
    alertEl.dataset.dismissTimer = String(setTimeout(closeAlert, timeoutMs));

    const closeButton = alertEl.querySelector('.btn-close');
    if (closeButton) {
      closeButton.addEventListener('click', () => {
        clearTimeout(Number(alertEl.dataset.dismissTimer));
      }, { once: true });
    }
  });

  function initCartas() {
    const buttons = document.querySelectorAll('.claim-card-button');
    const book = document.getElementById('albumBook');
    if (!buttons.length || !book) {
      return;
    }

    const pages = Array.from(book.querySelectorAll('.album-page'));
    const previousPage = document.getElementById('previousPage');
    const nextPage = document.getElementById('nextPage');
    const pageIndicator = document.getElementById('pageIndicator');
    const albumSearch = document.getElementById('albumSearch');
    let currentPage = 0;
    let isFlipping = false;

    function updatePageControls() {
      if (pageIndicator) pageIndicator.textContent = `Página ${currentPage + 1} de ${pages.length}`;
      if (previousPage) previousPage.disabled = currentPage === 0 || isFlipping;
      if (nextPage) nextPage.disabled = currentPage === pages.length - 1 || isFlipping;
    }

    function showPage(index, animate = true) {
      const nextPageIndex = Math.max(0, Math.min(index, pages.length - 1));
      if (nextPageIndex === currentPage) {
        pages.forEach((page, pageIndex) => page.classList.toggle('is-active', pageIndex === currentPage));
        return;
      }

      if (isFlipping) return;
      const direction = nextPageIndex > currentPage ? 'next' : 'previous';
      const updatePage = () => {
        currentPage = nextPageIndex;
        pages.forEach((page, pageIndex) => page.classList.toggle('is-active', pageIndex === currentPage));
        updatePageControls();
      };

      if (!animate) {
        updatePage();
      } else {
        isFlipping = true;
        const currentPageElement = pages[currentPage];
        const nextPageElement = pages[nextPageIndex];
        currentPageElement.classList.add(`is-turning-out-${direction}`);
        nextPageElement.classList.add(`is-turning-in-${direction}`);
        window.setTimeout(updatePage, 390);
        window.setTimeout(() => {
          currentPageElement.classList.remove(`is-turning-out-${direction}`);
          nextPageElement.classList.remove(`is-turning-in-${direction}`);
          isFlipping = false;
          updatePageControls();
        }, 820);
      }

      updatePageControls();
    }

    function findPage() {
      const query = (albumSearch ? albumSearch.value : '').trim().toLowerCase();
      if (!query) {
        showPage(currentPage);
        return;
      }
      const matchIndex = pages.findIndex((page) => page.dataset.pageName.includes(query));
      if (matchIndex >= 0) showPage(matchIndex, false);
    }

    previousPage?.addEventListener('click', () => showPage(currentPage - 1));
    nextPage?.addEventListener('click', () => showPage(currentPage + 1));
    albumSearch?.addEventListener('input', findPage);
    showPage(0);

    function bindTilt(cardEl) {
      const img = cardEl.querySelector('.card-image');
      if (!img) return;
      let raf = null;

      cardEl.addEventListener('mousemove', (e) => {
        const rect = cardEl.getBoundingClientRect();
        const x = e.clientX - rect.left;
        const y = e.clientY - rect.top;
        const cx = rect.width / 2;
        const cy = rect.height / 2;
        const dx = (x - cx) / cx;
        const dy = (y - cy) / cy;
        const influence = Math.max(Math.abs(dx), Math.abs(dy));
        const cornerBoost = Math.pow(influence, 0.9);
        const maxRotateX = 18;
        const maxRotateY = 20;
        const rotateX = (-dy * maxRotateX * (0.18 + 0.82 * cornerBoost));
        const rotateY = (dx * maxRotateY * (0.18 + 0.82 * cornerBoost));
        const imageZ = 20 + 40 * cornerBoost;
        const skewMax = 8;
        const scaleMin = 0.95;
        const originX = Math.min(Math.max((x / rect.width) * 100, 0), 100);
        const originY = Math.min(Math.max((y / rect.height) * 100, 0), 100);

        img.style.transformOrigin = `${originX}% ${originY}%`;
        if (raf) cancelAnimationFrame(raf);
        raf = requestAnimationFrame(() => {
          const skewX = (-dx * skewMax * cornerBoost).toFixed(2);
          const skewY = (dy * skewMax * cornerBoost).toFixed(2);
          const scaleAxis = (1 - ((1 - scaleMin) * cornerBoost)).toFixed(3);
          img.style.transform = `perspective(1400px) rotateX(${rotateX}deg) rotateY(${rotateY}deg) translateZ(${imageZ}px) scale(${scaleAxis}) skewX(${skewX}deg) skewY(${skewY}deg)`;
          img.style.transition = 'transform 0.06s linear';
        });
      });

      cardEl.addEventListener('mouseleave', () => {
        if (raf) cancelAnimationFrame(raf);
        img.style.transform = '';
        img.style.transition = 'transform 0.6s cubic-bezier(.2,.8,.2,1)';
      });
    }

    function showPackOpening(newCards, onComplete) {
      const animation = document.getElementById('cardPackAnimation');
      if (!animation || newCards.length === 0) {
        onComplete();
        return;
      }

      animation.innerHTML = `
        <div class="pack-opening-content">
          <span class="pack-opening-label">SOBRE ABIERTO</span>
          <div class="pack-opening-cards">
            ${newCards.map((src, index) => `<img src="${src}" alt="Carta obtenida ${index + 1}" class="pack-card pack-card-${index + 1}">`).join('')}
          </div>
        </div>`;
      animation.classList.add('is-visible');
      window.setTimeout(() => {
        animation.classList.remove('is-visible');
        window.setTimeout(() => {
          animation.innerHTML = '';
          onComplete();
        }, 280);
      }, 1450);
    }

    buttons.forEach((btn) => btn.addEventListener('click', function () {
      const selectedPack = btn.dataset.pack;
      buttons.forEach((button) => { button.disabled = true; });
      fetch('/desbloquear_cartas', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pack: selectedPack }),
        credentials: 'same-origin'
      }).then(async (r) => {
        const data = await r.json().catch(() => ({}));
        const images = data.cards || [];
        if (r.status === 402) {
          const messageNode = document.getElementById('cardMessage');
          if (messageNode) messageNode.textContent = data.message || 'No tienes puntos suficientes.';
          buttons.forEach((button) => { button.disabled = button.dataset.pack === 'plus' && button.textContent.includes('Solo miembros'); });
          return;
        }

        if (!r.ok) {
          const messageNode = document.getElementById('cardMessage');
          if (messageNode) messageNode.textContent = data.message || 'No se pudo reclamar la recompensa.';
          buttons.forEach((button) => { button.disabled = button.dataset.pack === 'plus' && button.textContent.includes('Solo miembros'); });
          return;
        }

        if (images.length === 0 && data.message) {
          const messageNode = document.getElementById('cardMessage');
          if (messageNode) messageNode.textContent = data.message;
          if (data.button_text) {
            btn.innerText = data.button_text;
            btn.disabled = data.disabled;
          }
          return;
        }

        btn.disabled = true;
        showPackOpening(data.new_cards || images.slice(-2), () => window.location.reload());
      }).catch((err) => {
        console.error('Error al desbloquear cartas', err);
        const messageNode = document.getElementById('cardMessage');
        if (messageNode) messageNode.textContent = 'Error al obtener cartas.';
        buttons.forEach((button) => { button.disabled = button.dataset.pack === 'plus' && button.textContent.includes('Solo miembros'); });
      });
    }));

    document.querySelectorAll('.album-card, .card-item').forEach(bindTilt);
    const obs = new MutationObserver((mutations) => {
      mutations.forEach((mutation) => {
        mutation.addedNodes.forEach((node) => {
          if (!node.querySelectorAll) return;
          node.querySelectorAll('.album-card, .card-item').forEach(bindTilt);
        });
      });
    });
    obs.observe(book, { childList: true, subtree: true });
  }

  function initBuscaminas() {
    const grid = document.getElementById('buscaminas-grid');
    const statusText = document.getElementById('buscaminas-status');
    const victoryMessage = document.getElementById('buscaminas-victory');
    const resetButton = document.getElementById('reset-buscaminas');
    const difficultyButtons = document.querySelectorAll('.difficulty-button');
    if (!grid || !statusText || !resetButton || difficultyButtons.length === 0) {
      return;
    }

    const difficultyConfig = {
      facil: { rows: 6, cols: 6, bombs: 6 },
      medio: { rows: 8, cols: 8, bombs: 10 },
      dificil: { rows: 10, cols: 10, bombs: 20 },
      extremo: { rows: 12, cols: 12, bombs: 35 }
    };

    const pointsByDifficulty = {
      facil: 10,
      medio: 50,
      dificil: 100,
      extremo: 300
    };

    let currentDifficulty = 'facil';
    let rows = 6;
    let cols = 6;
    let bombCount = 6;
    let revealedCount = 0;
    let flagsCount = 0;
    let gameOver = false;
    let bombsPlaced = false;
    let victoryAwarded = false;
    let cells = [];

    function setStatus(text) {
      statusText.textContent = text;
    }

    function updateStatus() {
      const remaining = bombCount - flagsCount;
      const totalCells = rows * cols;
      setStatus(`${remaining} bombas restantes | ${totalCells} celdas | ${flagsCount} banderas`);
    }

    function updatePointsBadges(pointsValue) {
      document.querySelectorAll('.points-badge').forEach((badge) => {
        badge.textContent = `🟠 ${pointsValue}`;
      });
    }

    async function awardVictoryPoints() {
      const points = pointsByDifficulty[currentDifficulty] || 0;
      if (!points || victoryAwarded) {
        return;
      }

      victoryAwarded = true;
      try {
        const response = await fetch('/minijuego_buscaminas/resultado', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'same-origin',
          body: JSON.stringify({ difficulty: currentDifficulty })
        });

        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
          throw new Error(data.error || 'No se pudo guardar el resultado');
        }

        if (data.total_points !== undefined) {
          updatePointsBadges(data.total_points);
        }

        if (victoryMessage) {
          victoryMessage.textContent = data.message || `¡GANASTE! +${points} puntos`;
          victoryMessage.hidden = false;
        }
      } catch (error) {
        console.error('Error al guardar el resultado del buscaminas', error);
        if (victoryMessage) {
          victoryMessage.textContent = `¡GANASTE! Pero no se pudieron guardar tus puntos.`;
          victoryMessage.hidden = false;
        }
      }
    }

    function createCell(row, col) {
      const cell = document.createElement('button');
      cell.type = 'button';
      cell.className = 'buscaminas-cell';
      cell.dataset.row = row;
      cell.dataset.col = col;
      cell.dataset.bomb = 'false';
      cell.dataset.revealed = 'false';
      cell.dataset.flagged = 'false';
      cell.addEventListener('click', handleLeftClick);
      cell.addEventListener('contextmenu', handleRightClick);
      return cell;
    }

    function buildGrid() {
      grid.innerHTML = '';
      grid.style.gridTemplateColumns = `repeat(${cols}, minmax(40px, 1fr))`;
      cells = [];
      for (let r = 0; r < rows; r += 1) {
        const rowCells = [];
        for (let c = 0; c < cols; c += 1) {
          const cell = createCell(r, c);
          grid.appendChild(cell);
          rowCells.push(cell);
        }
        cells.push(rowCells);
      }
    }

    function neighbors(row, col) {
      const coords = [];
      for (let dr = -1; dr <= 1; dr += 1) {
        for (let dc = -1; dc <= 1; dc += 1) {
          if (dr === 0 && dc === 0) continue;
          const nr = row + dr;
          const nc = col + dc;
          if (nr >= 0 && nr < rows && nc >= 0 && nc < cols) {
            coords.push({ row: nr, col: nc });
          }
        }
      }
      return coords;
    }

    function countNearbyBombs(row, col) {
      return neighbors(row, col).reduce((count, coord) => {
        return count + (cells[coord.row][coord.col].dataset.bomb === 'true' ? 1 : 0);
      }, 0);
    }

    function placeBombs(firstClickRow, firstClickCol) {
      let placed = 0;
      const forbidden = new Set();
      forbidden.add(`${firstClickRow},${firstClickCol}`);
      neighbors(firstClickRow, firstClickCol).forEach(({ row, col }) => {
        forbidden.add(`${row},${col}`);
      });

      while (placed < bombCount) {
        const r = Math.floor(Math.random() * rows);
        const c = Math.floor(Math.random() * cols);
        const key = `${r},${c}`;
        const cell = cells[r][c];
        if (cell.dataset.bomb === 'false' && !forbidden.has(key)) {
          cell.dataset.bomb = 'true';
          placed += 1;
        }
      }
      bombsPlaced = true;
    }

    function revealCell(cell) {
      if (cell.dataset.revealed === 'true' || cell.dataset.flagged === 'true') {
        return;
      }

      if (!bombsPlaced) {
        const row = parseInt(cell.dataset.row, 10);
        const col = parseInt(cell.dataset.col, 10);
        placeBombs(row, col);
      }

      cell.dataset.revealed = 'true';
      cell.classList.add('revealed');
      revealedCount += 1;

      if (cell.dataset.bomb === 'true') {
        cell.classList.add('bomb');
        cell.textContent = '💣';
        gameLost();
        return;
      }

      const row = parseInt(cell.dataset.row, 10);
      const col = parseInt(cell.dataset.col, 10);
      const bombsNear = countNearbyBombs(row, col);
      if (bombsNear > 0) {
        cell.textContent = bombsNear;
        cell.classList.add(`bomb-near-${bombsNear}`);
      } else {
        cell.textContent = '';
        neighbors(row, col).forEach(({ row: nr, col: nc }) => {
          revealCell(cells[nr][nc]);
        });
      }

      if (checkWin()) {
        gameWon();
      }
    }

    function revealAllBombs() {
      cells.flat().forEach((cell) => {
        if (cell.dataset.bomb === 'true') {
          cell.classList.add('bomb', 'revealed');
          if (cell.dataset.flagged !== 'true') {
            cell.textContent = '💣';
          }
        }
      });
    }

    function gameLost() {
      gameOver = true;
      revealAllBombs();
      setStatus('¡Has perdido! Presiona Reiniciar para jugar otra vez.');
    }

    function gameWon() {
      if (gameOver) {
        return;
      }

      gameOver = true;
      const points = pointsByDifficulty[currentDifficulty] || 0;
      setStatus(`¡Felicidades! Completaste el nivel y ganas ${points} puntos.`);
      awardVictoryPoints();
    }

    function checkWin() {
      return revealedCount === rows * cols - bombCount;
    }

    function handleLeftClick(event) {
      if (gameOver) return;
      const cell = event.currentTarget;
      if (cell.dataset.flagged === 'true') return;
      revealCell(cell);
      updateStatus();
    }

    function handleRightClick(event) {
      event.preventDefault();
      if (gameOver) return;
      const cell = event.currentTarget;
      if (cell.dataset.revealed === 'true') return;

      const flagged = cell.dataset.flagged === 'true';
      if (flagged) {
        cell.dataset.flagged = 'false';
        cell.classList.remove('flagged');
        cell.textContent = '';
        flagsCount -= 1;
      } else if (flagsCount < bombCount) {
        cell.dataset.flagged = 'true';
        cell.classList.add('flagged');
        cell.textContent = '🚩';
        flagsCount += 1;
      }
      updateStatus();
    }

    function updateDifficulty(selected) {
      if (!difficultyConfig[selected]) return;
      currentDifficulty = selected;
      rows = difficultyConfig[selected].rows;
      cols = difficultyConfig[selected].cols;
      bombCount = difficultyConfig[selected].bombs;
      difficultyButtons.forEach((button) => {
        button.classList.toggle('active', button.dataset.difficulty === selected);
      });
      initializeGame();
    }

    function initializeGame() {
      revealedCount = 0;
      flagsCount = 0;
      gameOver = false;
      bombsPlaced = false;
      victoryAwarded = false;
      if (victoryMessage) {
        victoryMessage.hidden = true;
        victoryMessage.textContent = '¡GANASTE!';
      }
      buildGrid();
      updateStatus();
    }

    difficultyButtons.forEach((button) => {
      button.addEventListener('click', () => {
        updateDifficulty(button.dataset.difficulty);
      });
    });

    resetButton.addEventListener('click', initializeGame);
    initializeGame();
  }

  function initTetris() {
    const board = document.getElementById('tetris-board');
    const startButton = document.getElementById('tetris-start');
    const pauseButton = document.getElementById('tetris-pause');
    const scoreDisplay = document.getElementById('tetris-score');
    const messageDisplay = document.getElementById('tetris-message');
    const holdGrid = document.getElementById('tetris-hold-grid');
    const nextGrid = document.getElementById('tetris-next-grid');

    if (!board || !startButton || !pauseButton || !scoreDisplay || !messageDisplay || !holdGrid || !nextGrid) {
      return;
    }

    const rows = 16;
    const cols = 10;
    const cells = [];
    const holdCells = [];
    const nextCells = [];
    let boardMatrix = [];
    let currentPiece = null;
    let dropTimer = null;
    let score = 0;
    let isRunning = false;
    let bag = [];
    let holdPiece = null;
    let holdUsed = false;
    let queue = [];

    const shapes = {
      I: { color: '#23d3ff', matrix: [[1, 1, 1, 1]] },
      J: { color: '#6b7cff', matrix: [[1, 0, 0], [1, 1, 1]] },
      L: { color: '#ffac4d', matrix: [[0, 0, 1], [1, 1, 1]] },
      O: { color: '#ffe66d', matrix: [[1, 1], [1, 1]] },
      S: { color: '#7dff9b', matrix: [[0, 1, 1], [1, 1, 0]] },
      T: { color: '#d78dff', matrix: [[0, 1, 0], [1, 1, 1]] },
      Z: { color: '#ff7070', matrix: [[1, 1, 0], [0, 1, 1]] }
    };

    function makeEmptyBoard() {
      return Array.from({ length: rows }, () => Array(cols).fill(null));
    }

    function buildBoardCells() {
      board.innerHTML = '';
      boardMatrix = makeEmptyBoard();
      cells.length = 0;
      for (let r = 0; r < rows; r += 1) {
        for (let c = 0; c < cols; c += 1) {
          const cell = document.createElement('div');
          cell.className = 'tetris-cell';
          board.appendChild(cell);
          cells.push(cell);
        }
      }
    }

    function buildMiniGrids() {
      holdGrid.innerHTML = '';
      nextGrid.innerHTML = '';
      holdCells.length = 0;
      nextCells.length = 0;

      for (let i = 0; i < 16; i += 1) {
        const cell = document.createElement('div');
        cell.className = 'tetris-mini-cell';
        holdGrid.appendChild(cell);
        holdCells.push(cell);
      }

      for (let i = 0; i < 4; i += 1) {
        const pieceGrid = document.createElement('div');
        pieceGrid.className = 'tetris-mini-grid tetris-next-piece';
        pieceGrid.dataset.index = String(i);
        for (let j = 0; j < 16; j += 1) {
          const cell = document.createElement('div');
          cell.className = 'tetris-mini-cell';
          pieceGrid.appendChild(cell);
          nextCells.push(cell);
        }
        nextGrid.appendChild(pieceGrid);
      }
    }

    function updateScore() {
      scoreDisplay.textContent = String(score);
    }

    function drawBoard() {
      const displayMatrix = boardMatrix.map(row => [...row]);
      if (currentPiece) {
        currentPiece.matrix.forEach((row, r) => {
          row.forEach((value, c) => {
            if (!value) return;
            const boardRow = currentPiece.row + r;
            const boardCol = currentPiece.col + c;
            if (boardRow >= 0 && boardRow < rows && boardCol >= 0 && boardCol < cols) {
              displayMatrix[boardRow][boardCol] = currentPiece.color;
            }
          });
        });
      }

      cells.forEach((cell, index) => {
        const r = Math.floor(index / cols);
        const c = index % cols;
        const color = displayMatrix[r][c];
        cell.className = color ? 'tetris-cell filled' : 'tetris-cell';
        if (color) {
          cell.style.background = color;
          cell.style.borderColor = color;
        } else {
          cell.style.background = 'rgba(255,255,255,0.04)';
          cell.style.borderColor = 'rgba(255,255,255,0.05)';
        }
      });
    }

    function drawMiniGrids() {
      drawMiniGrid(holdCells, holdPiece ? holdPiece.matrix : null, holdPiece ? holdPiece.color : null);
      const nextPieces = queue.slice(0, 4);
      const nextGrids = Array.from(nextGrid.children);
      nextGrids.forEach((grid, idx) => {
        const piece = nextPieces[idx];
        grid.innerHTML = '';
        const miniCells = [];
        for (let i = 0; i < 16; i += 1) {
          const cell = document.createElement('div');
          cell.className = 'tetris-mini-cell';
          grid.appendChild(cell);
          miniCells.push(cell);
        }
        drawMiniGrid(miniCells, piece ? piece.matrix : null, piece ? piece.color : null);
      });
    }

    function drawMiniGrid(cellsForGrid, matrix, color) {
      const matrixToUse = matrix || [];
      cellsForGrid.forEach((cell, idx) => {
        const r = Math.floor(idx / 4);
        const c = idx % 4;
        const v = matrixToUse[r] && matrixToUse[r][c];
        cell.className = v ? 'tetris-mini-cell filled' : 'tetris-mini-cell';
        if (v) {
          cell.style.setProperty('--mini-color', color || '#e6ad4f');
          cell.style.background = color || '#e6ad4f';
          cell.style.borderColor = color || '#e6ad4f';
        } else {
          cell.style.background = 'rgba(255,255,255,0.04)';
          cell.style.borderColor = 'rgba(255,255,255,0.05)';
        }
      });
    }

    function randomType() {
      const keys = Object.keys(shapes);
      return keys[Math.floor(Math.random() * keys.length)];
    }

    function randomPiece(type = randomType()) {
      const template = shapes[type];
      return {
        type,
        matrix: template.matrix.map(row => [...row]),
        color: template.color,
        row: 0,
        col: Math.floor(cols / 2) - Math.ceil(template.matrix[0].length / 2)
      };
    }

    function refillQueue() {
      while (queue.length < 4) {
        const type = randomType();
        const piece = randomPiece(type);
        queue.push(piece);
      }
      drawMiniGrids();
    }

    function collides(piece, offsetRow = 0, offsetCol = 0) {
      for (let r = 0; r < piece.matrix.length; r += 1) {
        for (let c = 0; c < piece.matrix[r].length; c += 1) {
          if (!piece.matrix[r][c]) continue;
          const newRow = piece.row + r + offsetRow;
          const newCol = piece.col + c + offsetCol;
          if (newCol < 0 || newCol >= cols || newRow >= rows) return true;
          if (newRow >= 0 && boardMatrix[newRow][newCol]) return true;
        }
      }
      return false;
    }

    function mergePiece() {
      currentPiece.matrix.forEach((row, r) => {
        row.forEach((value, c) => {
          if (!value) return;
          const cellRow = currentPiece.row + r;
          const cellCol = currentPiece.col + c;
          if (cellRow >= 0 && cellRow < rows && cellCol >= 0 && cellCol < cols) {
            boardMatrix[cellRow][cellCol] = currentPiece.color;
          }
        });
      });
    }

    function clearLines() {
      let cleared = 0;
      for (let r = rows - 1; r >= 0; r -= 1) {
        if (boardMatrix[r].every(Boolean)) {
          boardMatrix.splice(r, 1);
          boardMatrix.unshift(Array(cols).fill(null));
          cleared += 1;
          r += 1;
        }
      }
      if (cleared > 0) {
        score += cleared * 100;
        updateScore();
      }
    }

    function freezePiece() {
      mergePiece();
      clearLines();
      nextTurn();
      drawBoard();
      drawMiniGrids();
    }

    function nextTurn() {
      if (!queue.length) {
        refillQueue();
      }
      currentPiece = queue.shift();
      currentPiece.row = 0;
      currentPiece.col = Math.floor(cols / 2) - Math.ceil(currentPiece.matrix[0].length / 2);
      queue.push(randomPiece(randomType()));
      holdUsed = false;
      if (collides(currentPiece, 0, 0)) {
        isRunning = false;
        messageDisplay.textContent = 'Fin de partida';
        if (dropTimer) {
          window.clearInterval(dropTimer);
          dropTimer = null;
        }
      }
      drawMiniGrids();
    }

    function dropPiece() {
      if (!currentPiece || !isRunning) return;
      if (!collides(currentPiece, 1, 0)) {
        currentPiece.row += 1;
        drawBoard();
        return;
      }
      freezePiece();
    }

    function softDrop() {
      if (!currentPiece || !isRunning) return;
      if (!collides(currentPiece, 1, 0)) {
        currentPiece.row += 1;
        drawBoard();
      } else {
        freezePiece();
      }
    }

    function dropToBottom() {
      if (!currentPiece || !isRunning) return;
      while (!collides(currentPiece, 1, 0)) {
        currentPiece.row += 1;
      }
      freezePiece();
    }

    function movePiece(deltaCol) {
      if (!currentPiece || !isRunning || collides(currentPiece, 0, deltaCol)) return;
      currentPiece.col += deltaCol;
      drawBoard();
    }

    function rotatePiece() {
      if (!currentPiece || !isRunning) return;
      const rotated = currentPiece.matrix[0].map((_, idx) =>
        currentPiece.matrix.map(row => row[idx]).reverse()
      );

      const offsets = [0, -1, 1, -2, 2];
      for (const offset of offsets) {
        const candidate = { ...currentPiece, matrix: rotated, col: currentPiece.col + offset };
        if (!collides(candidate, 0, 0)) {
          currentPiece.matrix = rotated;
          currentPiece.col += offset;
          drawBoard();
          return;
        }
      }
    }

    function holdCurrentPiece() {
      if (!currentPiece || !isRunning || holdUsed) return;
      if (!holdPiece) {
        holdPiece = { ...randomPiece(currentPiece.type), matrix: currentPiece.matrix.map(row => [...row]) };
        holdUsed = true;
        nextTurn();
      } else {
        const saved = { ...holdPiece, row: 0, col: Math.floor(cols / 2) - Math.ceil(holdPiece.matrix[0].length / 2) };
        holdPiece = { ...currentPiece, row: 0, col: Math.floor(cols / 2) - Math.ceil(currentPiece.matrix[0].length / 2) };
        currentPiece = { ...saved, row: 0, col: Math.floor(cols / 2) - Math.ceil(saved.matrix[0].length / 2) };
        holdUsed = true;
        if (collides(currentPiece, 0, 0)) {
          isRunning = false;
          messageDisplay.textContent = 'Fin de partida';
          if (dropTimer) {
            window.clearInterval(dropTimer);
            dropTimer = null;
          }
        }
      }
      drawBoard();
      drawMiniGrids();
    }

    function startGame() {
      boardMatrix = makeEmptyBoard();
      bag = [];
      queue = [];
      holdPiece = null;
      holdUsed = false;
      score = 0;
      updateScore();
      refillQueue();
      currentPiece = queue.shift();
      currentPiece.row = 0;
      currentPiece.col = Math.floor(cols / 2) - Math.ceil(currentPiece.matrix[0].length / 2);
      queue.push(randomPiece(randomType()));
      isRunning = true;
      messageDisplay.textContent = 'Jugando';
      if (dropTimer) window.clearInterval(dropTimer);
      dropTimer = window.setInterval(dropPiece, 550);
      drawBoard();
      drawMiniGrids();
    }

    function pauseGame() {
      if (!isRunning) return;
      isRunning = false;
      messageDisplay.textContent = 'Pausado';
      if (dropTimer) {
        window.clearInterval(dropTimer);
        dropTimer = null;
      }
    }

    function resetGame() {
      boardMatrix = makeEmptyBoard();
      score = 0;
      updateScore();
      isRunning = false;
      queue = [];
      holdPiece = null;
      holdUsed = false;
      messageDisplay.textContent = 'Listo';
      currentPiece = randomPiece();
      if (dropTimer) {
        window.clearInterval(dropTimer);
        dropTimer = null;
      }
      refillQueue();
      currentPiece = queue.shift();
      currentPiece.row = 0;
      currentPiece.col = Math.floor(cols / 2) - Math.ceil(currentPiece.matrix[0].length / 2);
      queue.push(randomPiece(randomType()));
      drawBoard();
      drawMiniGrids();
    }

    startButton.addEventListener('click', startGame);
    pauseButton.addEventListener('click', pauseGame);

    document.addEventListener('keydown', (event) => {
      if (!currentPiece || !isRunning) return;

      if (event.key === 'ArrowLeft') {
        event.preventDefault();
        movePiece(-1);
      } else if (event.key === 'ArrowRight') {
        event.preventDefault();
        movePiece(1);
      } else if (event.key === 'ArrowDown') {
        event.preventDefault();
        softDrop();
      } else if (event.key === 'ArrowUp') {
        event.preventDefault();
        rotatePiece();
      } else if (event.code === 'Space' || event.key === ' ') {
        event.preventDefault();
        dropToBottom();
      } else if (event.key.toLowerCase() === 'c') {
        event.preventDefault();
        holdCurrentPiece();
      }
    });

    buildBoardCells();
    buildMiniGrids();
    resetGame();
  }

  function initCardRequirements() {
    document.querySelectorAll('[data-card-requirements]').forEach((picker) => {
      const form = picker.closest('form');
      const totalInput = form?.querySelector('[data-requirements-total]');
      const outputInput = form?.querySelector('[data-requirements-output]');
      const quantityInputs = picker.querySelectorAll('input[data-game]');
      if (!form || !totalInput || !outputInput || !quantityInputs.length) return;

      function updateRequirements() {
        let total = 0;
        const requirements = [];
        quantityInputs.forEach((input) => {
          const quantity = Math.max(0, Number.parseInt(input.value, 10) || 0);
          input.value = quantity;
          total += quantity;
          if (quantity > 0) requirements.push(`${input.dataset.game}: ${quantity}`);
        });
        totalInput.value = total;
        outputInput.value = requirements.join('\n');
      }

      quantityInputs.forEach((input) => input.addEventListener('input', updateRequirements));
      form.addEventListener('submit', updateRequirements);
      updateRequirements();
    });
  }

  initCartas();
  initBuscaminas();
  initTetris();
  initCardRequirements();
  initSearchAutocomplete();
});

  function initSearchAutocomplete() {
    const searchInput = document.querySelector('.search-input');
    const suggestionBox = document.getElementById('search-suggestions');
    if (!searchInput || !suggestionBox) {
      return;
    }

    const games = Array.from(document.querySelectorAll('.game-card')).map((card) => {
      const titleEl = card.querySelector('h3');
      const anchor = card.querySelector('a.btn-game[href]');
      return titleEl && anchor ? { title: titleEl.textContent.trim(), url: anchor.href } : null;
    }).filter(Boolean);

    if (games.length === 0) {
      return;
    }

    function renderSuggestions(filteredGames) {
      suggestionBox.innerHTML = '';
      if (filteredGames.length === 0) {
        const none = document.createElement('div');
        none.className = 'search-suggestion-noresults';
        none.textContent = 'No se encontraron juegos';
        suggestionBox.appendChild(none);
        suggestionBox.classList.add('visible');
        return;
      }

      filteredGames.forEach((game) => {
        const item = document.createElement('div');
        item.className = 'search-suggestion-item';
        item.textContent = game.title;
        item.addEventListener('click', () => {
          window.location.href = game.url;
        });
        suggestionBox.appendChild(item);
      });
      suggestionBox.classList.add('visible');
    }

    function updateSuggestions() {
      const query = searchInput.value.trim().toLowerCase();
      const filtered = query === ''
        ? games
        : games.filter((game) => game.title.toLowerCase().includes(query));
      renderSuggestions(filtered.slice(0, 8));
    }

    searchInput.addEventListener('input', updateSuggestions);
    searchInput.addEventListener('focus', updateSuggestions);
    document.addEventListener('click', (event) => {
      if (!suggestionBox.contains(event.target) && event.target !== searchInput) {
        suggestionBox.classList.remove('visible');
      }
    });
  }
