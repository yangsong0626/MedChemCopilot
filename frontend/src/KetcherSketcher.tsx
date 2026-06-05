import { useEffect, useRef } from "react";
import { Editor } from "ketcher-react";
import "ketcher-react/dist/index.css";
import { StandaloneStructServiceProvider } from "ketcher-standalone";
import type { Ketcher } from "ketcher-core";

const structServiceProvider = new StandaloneStructServiceProvider();

type KetcherSketcherProps = {
  smiles: string;
  onReady: (ketcher: Ketcher) => void;
  onError: (message: string) => void;
};

export default function KetcherSketcher({ smiles, onReady, onError }: KetcherSketcherProps) {
  const editorRef = useRef<Ketcher | null>(null);

  useEffect(() => {
    if (!editorRef.current || !smiles.trim()) return;
    editorRef.current.setMolecule(smiles).catch((error: unknown) => {
      onError(error instanceof Error ? error.message : String(error));
    });
  }, [smiles]);

  return (
    <div className="ketcher-shell">
      <Editor
        staticResourcesUrl="/"
        structServiceProvider={structServiceProvider}
        errorHandler={onError}
        onInit={async (ketcher) => {
          editorRef.current = ketcher;
          onReady(ketcher);
          if (smiles.trim()) {
            await ketcher.setMolecule(smiles);
          }
        }}
        disableMacromoleculesEditor
      />
    </div>
  );
}
