(() => {
  let dialog;

  function node(tag, text, className) {
    const element = document.createElement(tag);
    if (text) element.textContent = text;
    if (className) element.className = className;
    return element;
  }

  function button(label, action) {
    const element = node('button', label, 'secondary-button');
    element.type = 'button';
    element.onclick = action;
    return element;
  }

  function frame(chat, version, lazy = false) {
    const element = node('iframe', null, 'visual-prototype-frame');
    element.setAttribute('sandbox', '');
    element.referrerPolicy = 'no-referrer';
    element.title = version.title + ' · 視覺原型';
    element.loading = lazy ? 'lazy' : 'eager';
    element.src = '/chat-visual/' + encodeURIComponent(chat) + '/' + encodeURIComponent(version.turn);
    return element;
  }

  function open(chat, selected, versions) {
    close();
    const indices = new Map(versions.map((version, index) => [version.turn, index + 1]));
    const window = node('dialog', null, 'visual-prototype-dialog');
    dialog = window;
    window.setAttribute('aria-labelledby', 'visual-prototype-heading');
    const heading = node('h2', '視覺原型');
    heading.id = 'visual-prototype-heading';
    const bar = node('header', null, 'visual-prototype-header');
    bar.append(heading, button('關閉預覽', close));
    const hint = node('p', '這是設計預覽，畫面上的控制項未連接產品功能。');
    const controls = node('div', null, 'visual-prototype-controls');
    const canvas = node('div', null, 'visual-prototype-previews');
    let compact = false;
    let compare = false;
    let primary = selected.turn;
    let secondary = selected.parent || versions.find(version => version.turn !== primary)?.turn;

    function render() {
      canvas.classList.toggle('visual-compact', compact);
      canvas.classList.toggle('visual-compare', compare);
      const picks = compare ? [secondary, primary] : [primary];
      canvas.replaceChildren(...picks.map(turn => {
        const version = versions.find(record => record.turn === turn);
        const panel = node('figure', null, 'visual-prototype-version');
        panel.append(node('figcaption', '版本 ' + indices.get(turn) + ' · ' + version.title), frame(chat, version));
        return panel;
      }));
    }

    function picker(label, value, choose) {
      const field = node('label', label + ' ');
      const select = node('select');
      for (const version of versions) {
        const option = node('option', '版本 ' + indices.get(version.turn) + ' · ' + version.title);
        option.value = version.turn;
        option.selected = option.value === value;
        select.append(option);
      }
      select.onchange = () => { choose(select.value); render(); };
      field.append(select);
      return field;
    }
    const changeWidth = button('窄版預覽', () => {
      compact = !compact;
      canvas.classList.toggle('visual-compact', compact);
      changeWidth.textContent = compact ? '寬版預覽' : '窄版預覽';
    });
    controls.append(picker('版本', primary, value => { primary = value; }), changeWidth);
    if (versions.length > 1) {
      const against = picker('比較版本', secondary, value => { secondary = value; });
      against.hidden = true;
      const showBoth = button('並排比較', () => {
        compare = !compare;
        against.hidden = !compare;
        showBoth.textContent = compare ? '單一版本' : '並排比較';
        render();
      });
      controls.append(showBoth, against);
    }
    window.append(bar, hint, controls, canvas);
    window.addEventListener('close', () => {
      window.remove();
      if (dialog === window) dialog = null;
    }, {once:true});
    document.body.append(window);
    render();
    window.showModal();
  }

  function close() {
    if (dialog?.open) {
      dialog.querySelector('.visual-prototype-previews').replaceChildren();
      dialog.close();
    }
    dialog = null;
  }

  function card(chat, version, versions) {
    const parents = new Map(versions.map(item => [item.turn, item.parent]));
    function root(turn) {
      while (parents.get(turn)) turn = parents.get(turn);
      return turn;
    }
    const family = root(version.turn);
    const related = versions.filter(item => root(item.turn) === family);
    const element = node('section', null, 'visual-prototype-card');
    const bar = node('header', null, 'visual-prototype-header');
    bar.append(node('h3', version.title), button('放大預覽', () => open(chat, version, related)));
    element.append(bar, node('p', '視覺原型 · 版本 ' + (related.indexOf(version) + 1) + ' · 僅供設計討論'),
                   frame(chat, version, true));
    return element;
  }

  window.NexusVisual = {card, close};
})();
