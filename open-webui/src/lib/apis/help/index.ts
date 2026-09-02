import { WEBUI_API_BASE_URL } from '$lib/constants';

// ------------------------------
// 类型定义（与后端 Pydantic 模型对齐）
// ------------------------------
export interface HelpDocSummary {
	id: string;
	title: string;
	description: string;
	updated_at: number;
}

export interface HelpDocDetail extends HelpDocSummary {
	content: string; // Markdown 原文
}

export interface HelpDocListResponse {
	docs: HelpDocSummary[];
}

// ------------------------------
// 文档列表
// ------------------------------
export const getHelpDocList = async (
	token: string = ''
): Promise<HelpDocListResponse | null> => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/help/docs`, {
		method: 'GET',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			authorization: `Bearer ${token}`
		}
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.then((json) => json as HelpDocListResponse)
		.catch((err) => {
			error = err?.detail ?? err;
			console.error('[help] getHelpDocList error:', err);
			return null;
		});

	if (error) throw error;
	return res;
};

// ------------------------------
// 单篇文档详情（含 Markdown 正文）
// ------------------------------
export const getHelpDocById = async (
	token: string = '',
	docId: string
): Promise<HelpDocDetail | null> => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/help/docs/${encodeURIComponent(docId)}`, {
		method: 'GET',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			authorization: `Bearer ${token}`
		}
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.then((json) => json as HelpDocDetail)
		.catch((err) => {
			error = err?.detail ?? err;
			console.error(`[help] getHelpDocById(${docId}) error:`, err);
			return null;
		});

	if (error) throw error;
	return res;
};
