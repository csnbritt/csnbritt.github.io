---
layout: default
title: About
---

Hi, welcome to my personal site. I'm currently working on De Novo Chem, a company I cofounded to make access to chemical reaction search more affordable. Before that, I worked for a small consulting company called CS Squared LLC that worked with the Department of Defense to apply techniques used by pharmaceutical companies to discover new energetic materials.

## Interests

I'm currently interested in using large language models to catalog chemical knowledge so that it is accessible and useful to both humans and agents. LLMs today do an excellent job of finding references and information if it is explicitly described, but are much less reliable when it is not. I'm interested in building tools that can help bridge this gap.

More generally, I am interested in applying new technology, especially AI/ML, to make the development of useful chemical matter cheaper and faster. I am also passionate about open-source and the role that it will play in achieving this. 

- Research area one
- Research area two
- Something you're building or learning

## Recent posts

<ul class="post-list">
{% for post in site.posts limit:5 %}
  <li>
    <span class="post-date">{{ post.date | date: "%b %-d, %Y" }}</span>
    <a href="{{ post.url | relative_url }}">{{ post.title }}</a>
  </li>
{% endfor %}
</ul>

<p><a href="{{ '/blog/' | relative_url }}">All posts &rarr;</a></p>
