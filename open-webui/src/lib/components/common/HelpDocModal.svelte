<script lang="ts">
	import { getContext, onMount, tick } from 'svelte';
	import { marked, type Tokens } from 'marked';
	import DOMPurify from 'dompurify';

	import { getHelpDocById, type HelpDocDetail } from '$lib/apis/help';

	import Modal from '$lib/components/common/Modal.svelte';
	import Spinner from '$lib/components/common/Spinner.svelte';
	import XMark from '$lib/components/icons/XMark.svelte';

	const i18n = getContext('i18n');

	// 由外部 bind:show 控制显隐
	export let show = false;
	// 默认加载项目说明文档
	export let docId: string = 'project-guide';

	let loading = false;
	let errorMessage = '';
	let doc: HelpDocDetail | null = null;
	let renderedHtml = '';

	// 已成功加载的文档缓存：docId -> {doc, html}，避免重复请求
	const cache = new Map<string, { doc: HelpDocDetail; html: string }>();

	/**
	 * 将 Markdown 原文渲染为安全的 HTML 字符串
	 * 使用 marked 解析 + DOMPurify XSS 过滤
	 */
	const renderMarkdown = (md: string): string => {
		try {
			// marked 默认配置：启用 GFM（表格、任务列表、删除线）
			const rawHtml = marked.parse(md, {
				gfm: true,
				breaks: false
			}) as string;
			// DOMPurify 白名单清洗，防止恶意 script/iframe
			return DOMPurify.sanitize(rawHtml, {
				ADD_ATTR: ['target'] // 允许链接 target="_blank"
			});
		} catch (e) {
			console.error('[HelpDocModal] Markdown 渲染失败:', e);
			return `<pre class="text-red-500">文档渲染错误：${String(e)}</pre>`;
		}
	};

	/**
	 * 加载文档：优先走缓存，缓存未命中再调 API
	 */
	const loadDoc = async () => {
		// 缓存命中
		const cached = cache.get(docId);
		if (cached) {
			doc = cached.doc;
			renderedHtml = cached.html;
			return;
		}

		loading = true;
		errorMessage = '';
		try {
			const token = typeof localStorage !== 'undefined' ? localStorage.token ?? '' : '';
			const result = await getHelpDocById(token, docId);
			if (!result) {
				throw new Error('接口返回为空');
			}
			const html = renderMarkdown(result.content);
			doc = result;
			renderedHtml = html;
			cache.set(docId, { doc: result, html });
		} catch (e: any) {
			errorMessage = e?.detail ?? e?.message ?? String(e);
			console.error('[HelpDocModal] 加载文档失败:', e);
		} finally {
			loading = false;
			await tick();
		}
	};

	// 当 show 变为 true 时触发加载
	$: if (show && !doc) {
		loadDoc();
	}
	// 当 docId 切换且已打开时重新加载
	$: if (show && docId) {
		// 若缓存中没有，则清空 doc 以触发上面的 reactive load
		if (!cache.has(docId) && doc?.id !== docId) {
			doc = null;
			renderedHtml = '';
		}
	}

	// 关闭时重置错误信息（不清空 doc，保留缓存体验）
	const closeModal = () => {
		show = false;
		errorMessage = '';
	};
</script>

<Modal
	bind:show
	size="xl"
	className="bg-white dark:bg-gray-900 rounded-4xl flex flex-col max-h-[85vh]"
>
	<!-- Header：标题 + 关闭按钮 -->
	<div class="flex items-center justify-between px-5.5 pt-4 pb-3 border-b border-gray-200 dark:border-gray-800 shrink-0">
		<div class="flex flex-col min-w-0">
			<div class="text-lg font-semibold text-gray-900 dark:text-gray-100 truncate">
				{doc?.title || '项目说明文档'}
			</div>
			{#if doc?.updated_at}
				<div class="mt-0.5 text-xs text-gray-500 dark:text-gray-400">
					最后更新：{new Date(doc.updated_at * 1000).toLocaleString('zh-CN')}
				</div>
			{/if}
		</div>
		<button
			class="self-center rounded-lg p-1.5 text-gray-500 transition hover:bg-gray-100 hover:text-gray-700 dark:text-gray-400 dark:hover:bg-gray-800 dark:hover:text-gray-200"
			aria-label="关闭文档"
			title="关闭 (Esc)"
			on:click={closeModal}
		>
			<XMark className={'size-5'} />
		</button>
	</div>

	<!-- Body：加载态 / 错误态 / 内容 -->
	<div class="flex-1 overflow-y-auto scrollbar-thin">
		{#if loading}
			<div class="flex items-center justify-center py-24">
				<div class="flex flex-col items-center gap-3">
					<Spinner className="size-6" />
					<div class="text-sm text-gray-500 dark:text-gray-400">正在加载文档...</div>
				</div>
			</div>
		{:else if errorMessage}
			<div class="flex flex-col items-center justify-center py-20 px-6 text-center">
				<div class="mb-2 text-base font-medium text-red-600 dark:text-red-400">加载失败</div>
				<div class="mb-5 max-w-md text-sm text-gray-500 dark:text-gray-400 break-words">
					{errorMessage}
				</div>
				<button
					class="rounded-full bg-gray-100 px-4 py-2 text-sm text-gray-700 transition hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-200 dark:hover:bg-gray-700"
					on:click={loadDoc}
				>
					重新加载
				</button>
			</div>
		{:else if renderedHtml}
			<!--
        使用 @tailwindcss/typography 的 prose 类提供默认 Markdown 样式
        prose-gray dark:prose-invert 适配暗色主题
        max-w-none 去掉默认最大宽度限制，贴合 Modal 宽度
      -->
			<div
				class="px-5.5 py-5
                prose prose-gray dark:prose-invert
                prose-pre:bg-gray-100 dark:prose-pre:bg-gray-800
                prose-code:bg-gray-100 dark:prose-code:bg-gray-800 prose-code:rounded prose-code:px-1 prose-code:py-0.5
                prose-headings:text-gray-900 dark:prose-headings:text-gray-100
                prose-a:text-blue-600 dark:prose-a:text-blue-400
                max-w-none"
			>
				{@html renderedHtml}
			</div>
		{/if}
	</div>
</Modal>
