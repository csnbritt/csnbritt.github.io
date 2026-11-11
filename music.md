---
layout: default
title: Music
permalink: /music/
---

In college, I was a DJ for WRUW, the college radio station at Case Western Reserve University, where I mostly played shoegaze, dreampop, slowcore, and ambient music. Here are some of my favorite albums.

<div class="album-grid">
{% for album in site.data.albums %}
  <div class="album">
    {% if album.link %}<a href="{{ album.link }}">{% endif %}
    <img src="{{ album.cover | relative_url }}" alt="{{ album.title }} by {{ album.artist }}">
    {% if album.link %}</a>{% endif %}
    <p class="album-title">{{ album.title }}</p>
    <p class="album-artist">{{ album.artist }}</p>
    {% if album.note %}<p class="album-note">{{ album.note }}</p>{% endif %}
  </div>
{% endfor %}
</div>
