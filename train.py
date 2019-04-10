import torch
import os
from time import gmtime, strftime
import json

from models import RNN
from train_utils import evaluate, train
from batch_iterator import BatchIterator
from data_loader import load_transcription_embeddings_with_labels, load_mfcc_dataset, VAL_SIZE
from utils import timeit, log, log_major, log_success
from config import LinguisticConfig, AcousticConfig


MODEL_PATH = "saved_models"
TRANSCRIPTIONS_VAL_PATH = "data/iemocap_transcriptions_val.json"
TRANSCRIPTIONS_TRAIN_PATH = "data/iemocap_transcriptions_train.json"


def run_training(cfg, train_data, train_labels, val_data, val_labels):
    model_run_path = MODEL_PATH + "/" + strftime("%Y-%m-%d_%H:%M:%S", gmtime())
    model_weights_path = "{}/{}".format(model_run_path, cfg.model_weights_name)
    model_config_path = "{}/{}".format(model_run_path, cfg.model_config_name)
    result_path = "{}/result.txt".format(model_run_path)
    os.makedirs(model_run_path, exist_ok=True)

    """Choosing hardware"""
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    if device == "cuda":
        print("Using GPU. Setting default tensor type to torch.cuda.FloatTensor")
        torch.set_default_tensor_type("torch.cuda.FloatTensor")
    else:
        print("Using CPU. Setting default tensor type to torch.FloatTensor")
        torch.set_default_tensor_type("torch.FloatTensor")

    json.dump(cfg.to_json(), open(model_config_path, "w"))

    """Converting model to specified hardware and format"""
    model = RNN(cfg)
    model.float()
    model = model.to(device)

    """Defining loss and optimizer"""
    optimizer = torch.optim.Adam(model.parameters(), lr=cfg.lr)
    criterion = torch.nn.CrossEntropyLoss()
    criterion = criterion.to(device)

    """Creating data generators"""
    train_iterator = BatchIterator(train_data, train_labels, cfg.batch_size)
    validation_iterator = BatchIterator(val_data, val_labels, 100)

    train_loss = 999
    best_val_loss = 999
    train_acc = 0
    epochs_without_improvement = 0

    """Running training"""
    for epoch in range(cfg.n_epochs):
        train_iterator.shuffle()
        if epochs_without_improvement == cfg.patience:
            break

        val_loss, val_acc, val_weighted_acc, conf_mat = evaluate(model, validation_iterator, criterion)

        if val_loss < best_val_loss:
            torch.save(model.state_dict(), model_weights_path)
            best_val_loss = val_loss
            best_val_acc = val_acc
            best_val_weighted_acc = val_weighted_acc
            best_conf_mat = conf_mat
            epochs_without_improvement = 0
            log_success(" Epoch: {} | Val loss improved to {:.4f} | val acc: {:.3f} | weighted val acc: {:.3f} | train loss: {:.4f} | train acc: {:.3f} | saved model to {}.".format(
                epoch, best_val_loss, best_val_acc, best_val_weighted_acc, train_loss, train_acc, model_weights_path
            ))

        train_loss, train_acc, train_weighted_acc, _ = train(model, train_iterator, optimizer, criterion, cfg.reg_ratio)

        epochs_without_improvement += 1
    
        if not epoch % 1:
            log(f'| Epoch: {epoch+1} | Val Loss: {val_loss:.3f} | Val Acc: {val_acc*100:.2f}% '
                f'| Train Loss: {train_loss:.4f} | Train Acc: {train_acc*100:.3f}%', cfg.verbose)

    result = f'| Epoch: {epoch+1} | Val Loss: {best_val_loss:.3f} | Val Acc: {best_val_acc*100:.2f}% | Weighted Val Acc: {best_val_weighted_acc*100:.2f}% |' \
             f'Train Loss: {train_loss:.4f} | Train Acc: {train_acc*100:.3f}% \n Confusion matrix:\n {best_conf_mat}'
    log_major(result)
    log_major("Hyperparameters:{}".format(cfg.to_json()))
    with open(result_path, "w") as file:
        file.write(result)


if __name__ == "__main__":
    """Training linguistic data"""
    # cfg = LinguisticConfig()
    # val_features, val_labels = load_transcription_embeddings_with_labels(TRANSCRIPTIONS_VAL_PATH, cfg.seq_len)
    # train_features, train_labels = load_transcription_embeddings_with_labels(TRANSCRIPTIONS_TRAIN_PATH, cfg.seq_len)

    """Loading acoustic data"""
    cfg = AcousticConfig()
    mfcc_features, mfcc_labels = load_mfcc_dataset()
    train_features = mfcc_features[:VAL_SIZE]
    train_labels = mfcc_labels[:VAL_SIZE]
    val_features = mfcc_features[VAL_SIZE:]
    val_labels = mfcc_labels[VAL_SIZE:]

    """Running training"""
    run_training(cfg, train_features, train_labels, val_features, val_labels)
