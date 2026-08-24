import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";

import {
  EmptyState,
  ErrorState,
  SkeletonRows,
} from "../../components/StateViews";
import { useWorkspaceStore } from "../../stores/workspaceStore";
import { useCreateWorkspace, useTemplates } from "./useWorksQueries";

export default function WorksCreatePage() {
  const navigate = useNavigate();
  const templates = useTemplates();
  const createWorkspace = useCreateWorkspace();
  const setCurrentWorkspace = useWorkspaceStore(
    (state) => state.setCurrentWorkspace,
  );

  const [title, setTitle] = useState("");
  const [genre, setGenre] = useState("");
  const [description, setDescription] = useState("");
  const [selectedTemplate, setSelectedTemplate] = useState<string | null>(null);

  const canSubmit =
    title.trim().length > 0 && !createWorkspace.isPending;

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    if (!canSubmit) {
      return;
    }
    createWorkspace.mutate(
      {
        title: title.trim(),
        genre: genre.trim(),
        description: description.trim(),
      },
      {
        onSuccess: (created) => {
          setCurrentWorkspace({ id: created.id, title: created.title });
          navigate(`/works/${created.id}`);
        },
      },
    );
  };

  return (
    <section className="works-page works-page--form" data-testid="works-create-page">
      <header className="page-header">
        <h2>创建作品</h2>
        <Link className="text-link" to="/works">
          返回作品列表
        </Link>
      </header>
      <form className="works-form" onSubmit={handleSubmit}>
        <label className="form-field">
          <span className="form-label">书名（必填）</span>
          <input
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            placeholder="给作品起个名字"
            aria-label="作品标题"
            data-testid="works-title-input"
          />
        </label>
        <label className="form-field">
          <span className="form-label">类型</span>
          <input
            value={genre}
            onChange={(event) => setGenre(event.target.value)}
            placeholder="例如：网文 / 同人 / 正统"
            aria-label="作品类型"
          />
        </label>
        <label className="form-field">
          <span className="form-label">一句话简介</span>
          <textarea
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            placeholder="编辑部第一眼看到的故事轮廓"
            aria-label="作品简介"
            rows={3}
          />
        </label>
        <div className="template-picker" data-testid="template-picker">
          <p className="form-label">班子模板（可选参考）</p>
          {templates.isPending ? <SkeletonRows count={3} /> : null}
          {templates.isError ? (
            <ErrorState
              source="/templates"
              message={templates.error.message}
              onRetry={() => void templates.refetch()}
            />
          ) : null}
          {templates.isSuccess && templates.data.length === 0 ? (
            <EmptyState title="没有可用模板" />
          ) : null}
          {templates.isSuccess && templates.data.length > 0 ? (
            <ul className="template-list">
              <li>
                <label className="template-option">
                  <input
                    type="radio"
                    name="template"
                    checked={selectedTemplate === null}
                    onChange={() => setSelectedTemplate(null)}
                  />
                  <span className="template-option-body">
                    <span className="template-option-name">不使用模板</span>
                    <span className="template-option-desc">
                      按默认班子开张
                    </span>
                  </span>
                </label>
              </li>
              {templates.data.map((template) => (
                <li key={template.name}>
                  <label className="template-option">
                    <input
                      type="radio"
                      name="template"
                      checked={selectedTemplate === template.name}
                      onChange={() => setSelectedTemplate(template.name)}
                    />
                    <span className="template-option-body">
                      <span className="template-option-name">
                        {template.name}
                      </span>
                      <span className="template-option-desc">
                        {template.description}
                      </span>
                    </span>
                  </label>
                </li>
              ))}
            </ul>
          ) : null}
          <p className="form-hint">
            模板决定班子的气质与初始风格，当前版本先作参考展示，随创建提交的仍是书名 / 类型 / 简介。
          </p>
        </div>
        {createWorkspace.isError ? (
          <div
            className="inline-error"
            role="alert"
            data-testid="works-create-error"
          >
            创建失败：{createWorkspace.error.message}
          </div>
        ) : null}
        <button
          type="submit"
          className="primary-button"
          disabled={!canSubmit}
          data-testid="works-submit-button"
        >
          {createWorkspace.isPending ? "创建中…" : "创建作品"}
        </button>
      </form>
    </section>
  );
}
